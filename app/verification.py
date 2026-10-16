"""- Handle or ID locates; two correct details verify.
- The name is the only public detail.
- If another public detail appears, require a private match too.
"""

from __future__ import annotations

from . import data
from .state import SessionState

REQUIRED_MATCHES = 2


def try_verify(state: SessionState) -> tuple[bool, dict]:
    creator = data.find_creator(state.collected)
    if creator is None:
        return False, {"reason": "no_record", "matched": [], "match_count": 0,
                       "creator_id": None}

    matched = data.field_matches(creator, state.collected)
    verified = len(matched) >= REQUIRED_MATCHES
    if verified:
        state.verified_creator_id = creator["creator_id"]
    return verified, {
        "reason": "verified" if verified else "insufficient_matches",
        "matched": matched, "match_count": len(matched),
        "creator_id": creator["creator_id"] if verified else None,
    }
