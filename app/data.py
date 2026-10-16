"""Fixture lookups. Swap for real services."""

from __future__ import annotations

import json
import re
from functools import lru_cache

from . import config

_SUB_ID = re.compile(r"^SUB-\d+$", re.I)
VERIFICATION_FIELDS = ("full_name", "email", "payout_last4", "phone")


@lru_cache(maxsize=None)
def _load(name: str):
    return json.loads((config.FIXTURES_DIR / name).read_text())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def get_creator(creator_id: str) -> dict | None:
    return next((c for c in _load("creators.json") if c["creator_id"] == creator_id), None)


def find_creator(collected: dict) -> dict | None:
    if collected.get("creator_id"):
        want = collected["creator_id"].strip().upper()
        hit = next((c for c in _load("creators.json") if c["creator_id"] == want), None)
        if hit:
            return hit
    if collected.get("handle"):
        want = collected["handle"].strip().lstrip("@").lower()
        return next((c for c in _load("creators.json")
                     if c["handle"].lstrip("@").lower() == want), None)
    return None


def field_matches(creator: dict, provided: dict) -> list[str]:
    matched = []
    if provided.get("full_name") and _norm(provided["full_name"]) == _norm(creator["full_name"]):
        matched.append("full_name")
    if provided.get("email") and _norm(provided["email"]) == _norm(creator["email"]):
        matched.append("email")
    if provided.get("payout_last4") and _digits(provided["payout_last4"]) == creator["payout_last4"]:
        matched.append("payout_last4")
    if provided.get("phone") and _digits(provided["phone"])[-10:] == _digits(creator["phone"])[-10:]:
        matched.append("phone")
    return matched


def submissions_for(creator_id: str) -> list[dict]:
    return [s for s in _load("submissions.json") if s["creator_id"] == creator_id]


def get_submission_for(creator_id: str, submission_id: str) -> dict | None:
    return next((s for s in submissions_for(creator_id)
                 if s["submission_id"].upper() == (submission_id or "").upper()), None)


def get_brief(campaign_id: str) -> dict | None:
    return next((c for c in _load("campaigns.json") if c["campaign_id"] == campaign_id), None)


def describe(sub: dict) -> dict:
    camp = get_brief(sub["campaign_id"]) or {}
    return {"submission_id": sub["submission_id"], "title": sub["title"],
            "campaign": camp.get("name"), "submitted_at": sub["submitted_at"]}


def match_submissions_scored(creator_id: str, hints: list[str]) -> list[tuple[dict, int]]:
    scored = []
    for sub in submissions_for(creator_id):
        camp = get_brief(sub["campaign_id"]) or {}
        haystack = _norm(" ".join([sub["submission_id"], sub["title"], camp.get("name", ""),
                                   camp.get("brand", ""), camp.get("category", "")]))
        score = 0
        for hint in hints:
            h = _norm(hint)
            if not h:
                continue
            if _SUB_ID.match(h) and h.upper() == sub["submission_id"].upper():
                score += 100
            elif h in haystack:
                score += 30
            else:
                score += 10 * sum(1 for w in h.split() if len(w) >= 3 and w in haystack)
        if score > 0:
            scored.append((sub, score))
    return sorted(scored, key=lambda p: -p[1])


def stated_unmatched_submission_id(creator_id: str, hints: list[str]) -> str | None:
    mine = {s["submission_id"].upper() for s in submissions_for(creator_id)}
    for h in hints:
        if _SUB_ID.match((h or "").strip()) and h.strip().upper() not in mine:
            return h.strip().upper()
    return None


def choose_reviewer(category: str) -> dict:
    reviewers = _load("reviewers.json")
    pool = [r for r in reviewers if category in r["specialties"]] or reviewers
    return max(pool, key=lambda r: r["agreement_rate"])


def build_checklist(sub: dict, review_view: dict, recipient: str) -> str:
    lines = [f"Hi {recipient},", "",
             f"Here is your checklist for \"{sub['title']}\" ({sub['submission_id']}):", ""]
    for item in review_view["to_fix"]:
        lines.append(f"- {item['fix']}")
    lines += ["", "Upload the revised video and we will review it again."]
    return "\n".join(lines)


def build_delivery_record(body: str, destination: str | None) -> dict:
    """Demo only: nothing is sent."""
    return {"status": "simulated_not_sent" if destination else "no_destination_on_file",
            "destination_field": "account_email" if destination else None,
            "body": body}
