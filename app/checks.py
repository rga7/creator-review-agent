"""Review rules, no model.

- required: the creator can fix it
- blocker: needs a person
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from . import config


@dataclass
class CheckResult:
    id: str
    label: str
    passed: bool
    severity: str
    detail: str = ""
    fix: str = ""
    must_mention: list[str] = field(default_factory=list)
    creator_visible: bool = True


def _has_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase.lower())}(?!\w)", text.lower()) is not None


def _tags(values: list[str]) -> set[str]:
    return {v.strip().lower() for v in values}


def run_checks(brief: dict, sub: dict) -> list[CheckResult]:
    results: list[CheckResult] = []
    text = f"{sub.get('transcript', '')} {sub.get('caption', '')}"
    tags = _tags(sub.get("hashtags", []))
    mentions = _tags(sub.get("mentions", []))

    lo, hi = brief["duration_s"]["min"], brief["duration_s"]["max"]
    dur = sub.get("duration_s", 0)
    results.append(CheckResult(
        "duration", "video length", lo <= dur <= hi, "required",
        detail=f"{dur}s (allowed {lo}-{hi}s)",
        fix=f"Trim or extend the video to between {lo} and {hi} seconds (it is {dur}s now).",
        must_mention=[str(hi), str(lo)]))

    want = brief["aspect_ratio"]
    results.append(CheckResult(
        "aspect_ratio", "aspect ratio", sub.get("aspect_ratio") == want, "required",
        detail=f"{sub.get('aspect_ratio')} (needs {want})",
        fix=f"Re-export in {want} vertical format.", must_mention=[want]))

    disclosure = [d.lower() for d in brief["disclosure_tags"]]
    results.append(CheckResult(
        "disclosure", "paid-partnership disclosure", any(d in tags for d in disclosure),
        "required", detail="no disclosure tag found" if not any(d in tags for d in disclosure)
        else "disclosure present",
        fix=f"Add a disclosure such as {brief['disclosure_tags'][0]} to the caption.",
        must_mention=disclosure))

    for tag in brief["required_hashtags"]:
        ok = tag.lower() in tags
        results.append(CheckResult(
            f"hashtag:{tag}", f"required hashtag {tag}", ok, "required",
            detail="present" if ok else "missing",
            fix=f"Add {tag} to the caption.", must_mention=[tag]))

    for handle in brief["required_mentions"]:
        ok = handle.lower() in mentions
        results.append(CheckResult(
            f"mention:{handle}", f"brand mention {handle}", ok, "required",
            detail="present" if ok else "missing",
            fix=f"Tag {handle} in the caption.", must_mention=[handle]))

    for point in brief["talking_points"]:
        ok = any(_has_phrase(text, kw) for kw in point["any_of"])
        results.append(CheckResult(
            f"point:{point['id']}", f"talking point: {point['label']}", ok, "required",
            detail="covered" if ok else "not found in transcript or caption",
            fix=f"In the video, {point['label']}.",
            must_mention=list(point["any_of"]) + [point["id"]]))

    hits = [p for p in brief["banned_phrases"] if _has_phrase(text, p)]
    results.append(CheckResult(
        "banned_claims", "restricted claims", not hits, "blocker",
        detail=f"restricted wording found: {', '.join(hits)}" if hits else "none found",
        fix="A reviewer will check the restricted wording with you.",
        must_mention=hits))

    # Not shown to the creator: saying how duplicates are caught helps evade it.
    results.append(CheckResult(
        "originality", "originality check", not sub.get("duplicate_flag", False),
        "blocker", detail="flagged for originality review" if sub.get("duplicate_flag")
        else "no flag", fix="A reviewer will follow up.",
        creator_visible=False))
    return results


def decide(results: list[CheckResult], sub: dict) -> dict:
    failed = [r for r in results if not r.passed]
    blockers = [r for r in failed if r.severity == "blocker"]

    if blockers:
        decision, reason = "escalated", "blocker:" + ",".join(b.id for b in blockers)
    elif not failed:
        decision, reason = "approved", "all_checks_passed"
    elif sub.get("revision_count", 0) >= config.MAX_REVISIONS:
        decision, reason = "escalated", "revision_limit"
    else:
        decision, reason = "changes_requested", "required_checks_failed"
    return {"decision": decision, "reason": reason,
            "failed_ids": [r.id for r in failed],
            "checks": [asdict(r) for r in results]}


def creator_view(review: dict) -> dict:
    visible = [c for c in review["checks"] if c["creator_visible"]]
    return {
        "decision": review["decision"],
        "passed": [c["label"] for c in visible if c["passed"]],
        "to_fix": [{"label": c["label"], "found": c["detail"], "fix": c["fix"]}
                   for c in visible if not c["passed"] and c["severity"] == "required"],
        "flagged": [{"label": c["label"], "found": c["detail"]}
                    for c in visible if not c["passed"] and c["severity"] == "blocker"],
        "revision_limit_reached": review["reason"] == "revision_limit",
    }


def reply_must_cover(review: dict) -> dict:
    """Words the reply backstop looks for. Separate from creator_view so they stay server-side."""
    visible = [c for c in review["checks"] if c["creator_visible"] and not c["passed"]]
    return {
        "fixes": [{"fix": c["fix"], "tokens": c["must_mention"]}
                  for c in visible if c["severity"] == "required"],
        "flagged": [{"found": c["detail"], "tokens": c["must_mention"]}
                    for c in visible if c["severity"] == "blocker"],
    }
