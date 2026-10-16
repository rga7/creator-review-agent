"""Per-turn flow: extract, remember, gates, phase action, generate. Only this module changes phase."""

from __future__ import annotations

from . import audit, checks, config, consent, data, llm, metrics, verification
from .actions import Kind
from .state import Phase, SessionState
from .validation import sanitize_control_injection


def handle_turn(state: SessionState, user_message: str) -> str:
    user_message = sanitize_control_injection(user_message)
    state.add_turn("user", user_message)

    ext = llm.extract(user_message, state.public_snapshot())
    before = len(state.rejected_fields)
    accepted = state.remember(ext, message=user_message)
    if len(state.rejected_fields) > before:
        audit.pii_provenance_rejected(state.session_id, state.rejected_fields[before:])

    if state.phase == Phase.HUMAN_ESCALATION:
        return _human_followup(state, user_message)

    if ext.get("wants_human"):
        return _escalate(state, "explicit_request", {"kind": Kind.HUMAN}, user_message)

    if state.frustration_count >= config.FRUSTRATION_LIMIT:
        return _escalate(state, "frustration_limit",
                         {"kind": Kind.HUMAN, "emotion": state.emotion}, user_message)

    if ext.get("in_scope") is False:
        if state.offtopic_count > config.OFFTOPIC_LIMIT:
            return _escalate(state, "offtopic_limit", {"kind": Kind.OFFTOPIC_HUMAN}, user_message)
        return _say(state, {"kind": Kind.OFFTOPIC}, None, user_message)

    # Switching submissions: reset and re-resolve.
    if ext.get("intent") == "other_submission" and \
            state.phase in (Phase.REVIEW, Phase.WRAP_UP, Phase.DONE):
        state._reset_submission_dependent_state()
        state.sub_hints = list(ext.get("submission_hints") or [])

    if state.phase == Phase.VERIFY_ID:
        return _verify(state, accepted, user_message)
    if state.phase == Phase.FIND_SUBMISSION:
        return _find_submission(state, user_message)
    if state.phase == Phase.REVIEW:
        return _review(state, ext, user_message)
    if state.phase == Phase.WRAP_UP:
        return _wrap_up(state, ext, user_message)
    return _say(state, {"kind": Kind.DONE}, None, user_message)


def _escalate(state: SessionState, reason: str, action: dict, user_message: str,
              reviewer: dict | None = None, grounded: dict | None = None) -> str:
    """Final: every later turn stays with the human."""
    state.phase = Phase.HUMAN_ESCALATION
    audit.human_escalation(state.session_id, reason, reviewer["reviewer_id"] if reviewer else None)
    return _say(state, action, grounded, user_message)


def _human_followup(state: SessionState, user_message: str) -> str:
    if state.review and state.escalation:
        return _say(state, {"kind": Kind.ESCALATED_FOLLOWUP,
                            "reviewer_name": state.escalation["name"]},
                    checks.creator_view(state.review), user_message)
    return _say(state, {"kind": Kind.HUMAN}, None, user_message)


def _verify(state: SessionState, accepted: set[str], user_message: str) -> str:
    verified, info = verification.try_verify(state)
    audit.verification_attempt(state.session_id, info["matched"], info["match_count"],
                               verified, info["creator_id"])

    if verified:
        state.phase = Phase.FIND_SUBMISSION
        ack = {"just_verified": True}
        if state.sub_hints or state.remembered_intent:
            return _find_submission(state, user_message, ack)
        return _say(state, {"kind": Kind.VERIFIED, "verified": True, **ack}, None, user_message)

    # Counts only if the creator gave identity details this turn.
    if accepted & set(data.VERIFICATION_FIELDS):
        state.failed_verifications += 1
    if state.failed_verifications >= config.MAX_VERIFY_FAILURES:
        audit.verification_lockout(state.session_id, state.failed_verifications)
        return _escalate(state, "verify_lockout", {"kind": Kind.VERIFY_LOCKOUT}, user_message)
    # Same reply whether or not the account exists.
    return _say(state, {
        "kind": Kind.NEED_MORE_DETAILS, "verified": False,
        "ask_for": [f for f in ("handle", *data.VERIFICATION_FIELDS)
                    if f not in state.collected],
    }, None, user_message)


def _candidates(creator_id: str) -> list[dict]:
    return [data.describe(s) for s in data.submissions_for(creator_id)]


def _find_submission(state: SessionState, user_message: str, ack: dict | None = None) -> str:
    creator = state.verified_creator_id
    ack = ack or {}

    if data.stated_unmatched_submission_id(creator, state.sub_hints):
        return _say(state, {"kind": Kind.RESOLVE_UNKNOWN_ID, "verified": True,
                            "candidates": _candidates(creator), **ack}, None, user_message)

    scored = data.match_submissions_scored(creator, state.sub_hints)
    if scored:
        top = scored[0][1]
        tied = [s for s, score in scored if score == top]
        if len(tied) > 1 and top < 100:
            return _say(state, {"kind": Kind.RESOLVE_AMBIGUOUS, "verified": True,
                                "candidates": [data.describe(s) for s in tied], **ack},
                        None, user_message)
        state.active_submission_id = scored[0][0]["submission_id"]
        state.phase = Phase.REVIEW
        return _review(state, {}, user_message, just_resolved=True, ack=ack)

    return _say(state, {"kind": Kind.RESOLVE_NEED_CLARIFY, "verified": True,
                        "candidates": _candidates(creator), **ack}, None, user_message)


def _run_review(state: SessionState) -> dict:
    """Runs once per submission. Follow-ups reuse the result."""
    sub = data.get_submission_for(state.verified_creator_id, state.active_submission_id)
    brief = data.get_brief(sub["campaign_id"])
    audit.submission_accessed(state.session_id, sub["submission_id"], state.verified_creator_id)
    review = checks.decide(checks.run_checks(brief, sub), sub)
    review["category"] = brief["category"]
    audit.review_decision(state.session_id, sub["submission_id"], review["decision"],
                          review["reason"], review["failed_ids"])
    return review


def _review(state: SessionState, ext: dict, user_message: str,
            just_resolved: bool = False, ack: dict | None = None) -> str:
    ack = ack or {}

    if state.review is None:
        state.review = _run_review(state)
        view = checks.creator_view(state.review)
        base = {"decision": state.review["decision"], "to_fix": view["to_fix"],
                "cover": checks.reply_must_cover(state.review), "verified": True, **ack}

        if state.review["decision"] == "escalated":
            reviewer = data.choose_reviewer(state.review["category"])
            state.escalation = reviewer
            return _escalate(
                state, state.review["reason"],
                {"kind": Kind.REVIEW_ESCALATED, **base, "flagged": view["flagged"],
                 "reviewer_name": reviewer["name"],
                 "revision_limit_reached": view["revision_limit_reached"]},
                user_message, reviewer=reviewer, grounded=view)
        return _say(state, {"kind": Kind.REVIEW_RESULT, **base}, view, user_message)

    if ext.get("conversation_wrapup") and not just_resolved:
        if state.review["decision"] == "changes_requested":
            state.phase = Phase.WRAP_UP
            return _say(state, {"kind": Kind.OFFER_EMAIL, "verified": True}, None, user_message)
        state.phase = Phase.DONE
        return _say(state, {"kind": Kind.CLOSING}, None, user_message)

    return _say(state, {"kind": Kind.REVIEW_FOLLOWUP, "verified": True},
                checks.creator_view(state.review), user_message)


def _wrap_up(state: SessionState, ext: dict, user_message: str) -> str:
    keyword = consent.parse_consent(user_message)
    model_map = {"grant": "yes", "deny": "no", "conditional": "conditional",
                 "defer": "deferred", "unclear": "ambiguous"}
    model_reading = ext.get("email_consent")
    if model_reading in model_map:
        parsed = model_map[model_reading]
        # A model "yes" also needs the keyword reading to say yes.
        if parsed == "yes" and keyword != "yes":
            parsed = keyword if keyword in ("no", "conditional", "deferred") else "ambiguous"
            metrics.incr("consent_conflict_failsafe")
    else:
        parsed = keyword

    if parsed == "yes":
        creator = data.get_creator(state.verified_creator_id)
        sub = data.get_submission_for(state.verified_creator_id, state.active_submission_id)
        state.summary = data.build_checklist(
            sub, checks.creator_view(state.review), creator["full_name"])
        # The address comes from the account record, not the chat.
        state.delivery = data.build_delivery_record(state.summary, creator.get("email"))
        if state.delivery["status"] == "no_destination_on_file":
            audit.email_consent(state.session_id, state.active_submission_id, "no_destination")
            return _escalate(state, "no_destination",
                             {"kind": Kind.EMAIL_FAILED, "verified": True}, user_message)
        state.consent_status = "approved"
        state.phase = Phase.DONE
        audit.email_consent(state.session_id, state.active_submission_id, "approved")
        return _say(state, {"kind": Kind.EMAIL_SENT, "verified": True,
                            "delivery_status": state.delivery["status"],
                            "checklist": state.summary}, None, user_message)
    if parsed == "no":
        state.consent_status = "skipped"
        state.phase = Phase.DONE
        audit.email_consent(state.session_id, state.active_submission_id, "skipped")
        return _say(state, {"kind": Kind.EMAIL_SKIPPED, "verified": True}, None, user_message)
    if parsed == "conditional":
        return _say(state, {"kind": Kind.EMAIL_CONDITIONAL, "verified": True}, None, user_message)
    if parsed == "deferred":
        return _say(state, {"kind": Kind.EMAIL_DEFERRED, "verified": True}, None, user_message)
    return _say(state, {"kind": Kind.OFFER_EMAIL, "verified": True}, None, user_message)


def _say(state: SessionState, action: dict, grounded: dict | None, user_message: str) -> str:
    action.setdefault("emotion", state.emotion)
    reply = llm.generate_reply(state.phase.value, action, grounded, state.history, user_message)
    state.add_turn("assistant", reply)
    return reply
