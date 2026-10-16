"""Audit events. Logs ids, field names and outcomes, never the details a creator typed."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

audit_log = logging.getLogger("sop.audit")
if not audit_log.handlers:
    audit_log.addHandler(logging.StreamHandler())
    audit_log.setLevel(logging.INFO)
    audit_log.propagate = False


def _event(kind: str, session_id: str | None, **fields: Any) -> None:
    audit_log.info(json.dumps({"event": kind, "session_id": session_id,
                               "ts": round(time.time(), 3), **fields}))


def verification_attempt(session_id, matched_fields, match_count, verified, creator_id):
    _event("verification_attempt", session_id, matched_fields=matched_fields,
           match_count=match_count, verified=verified, creator_id=creator_id)


def verification_lockout(session_id, failures):
    _event("verification_lockout", session_id, failures=failures)


def pii_provenance_rejected(session_id, fields):
    _event("pii_provenance_rejected", session_id, fields=list(fields))


def submission_accessed(session_id, submission_id, creator_id):
    _event("submission_accessed", session_id, submission_id=submission_id,
           creator_id=creator_id)


def review_decision(session_id, submission_id, decision, reason, failed_checks):
    _event("review_decision", session_id, submission_id=submission_id,
           decision=decision, reason=reason, failed_checks=failed_checks)


def human_escalation(session_id, reason, reviewer_id=None):
    _event("human_escalation", session_id, reason=reason, reviewer_id=reviewer_id)


def email_consent(session_id, submission_id, outcome):
    _event("email_consent", session_id, submission_id=submission_id, outcome=outcome)


def rate_limited(session_id, key):
    _event("rate_limited", session_id, key=key)
