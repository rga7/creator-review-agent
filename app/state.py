from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_SUB_ID = re.compile(r"^SUB-\d+$", re.I)


class Phase(str, Enum):
    VERIFY_ID = "VERIFY_ID"
    FIND_SUBMISSION = "FIND_SUBMISSION"
    REVIEW = "REVIEW"
    WRAP_UP = "WRAP_UP"
    DONE = "DONE"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"


def pii_value_in_message(field_name: str, value: str, message: str) -> bool:
    """True if the extracted value appears in the creator's message."""
    if not value or not message:
        return False
    msg = message.lower()

    if field_name in ("phone", "payout_last4"):
        digits = re.sub(r"\D", "", value)
        msg_digits = re.sub(r"\D", "", message)
        if not digits:
            return False
        if digits in msg_digits:
            return True
        return field_name == "phone" and len(digits) >= 10 and digits[-10:] in msg_digits

    if field_name == "handle":
        return value.strip().lstrip("@").lower() in msg

    norm_val = re.sub(r"\s+", " ", value.strip().lower())
    norm_msg = re.sub(r"\s+", " ", msg)
    return norm_val in norm_msg


@dataclass
class SessionState:
    session_id: str
    phase: Phase = Phase.VERIFY_ID

    collected: dict[str, str] = field(default_factory=dict)
    rejected_fields: list[str] = field(default_factory=list)
    verified_creator_id: str | None = None
    failed_verifications: int = 0

    remembered_intent: str | None = None
    sub_hints: list[str] = field(default_factory=list)

    active_submission_id: str | None = None
    review: dict | None = None
    escalation: dict | None = None

    emotion: str = "neutral"
    frustration_count: int = 0
    offtopic_count: int = 0

    consent_status: str | None = None  # None | "approved" | "skipped"
    summary: str | None = None
    delivery: dict | None = None

    history: list[dict[str, str]] = field(default_factory=list)
    last_seen: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add_turn(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    def _reset_submission_dependent_state(self) -> None:
        """Also clears consent, so a later "yes" cannot send the old submission's checklist."""
        self.active_submission_id = None
        self.review = None
        self.escalation = None
        if self.phase in (Phase.REVIEW, Phase.WRAP_UP, Phase.DONE):
            self.phase = Phase.FIND_SUBMISSION
        self.consent_status = None
        self.summary = None
        self.delivery = None

    def remember(self, ext: dict[str, Any], message: str = "") -> set[str]:
        """Returns the identity fields accepted this turn."""
        accepted: set[str] = set()
        for k, v in (ext.get("pii") or {}).items():
            if not v:
                continue
            if message and not pii_value_in_message(k, v, message):
                self.rejected_fields.append(k)
                continue
            self.collected[k] = v
            accepted.add(k)

        if ext.get("intent"):
            self.remembered_intent = ext["intent"]

        hints = ext.get("submission_hints") or []
        new_ids = [h for h in hints if _SUB_ID.match(h or "")]
        if new_ids:
            self.sub_hints = [h for h in self.sub_hints if not _SUB_ID.match(h or "")]
        for hint in hints:
            if hint and hint not in self.sub_hints:
                self.sub_hints.append(hint)
        if new_ids and self.active_submission_id and \
                self.active_submission_id.upper() not in {i.upper() for i in new_ids}:
            self._reset_submission_dependent_state()

        self.emotion = ext.get("emotion") or "neutral"
        if self.emotion in {"frustrated", "angry", "anxious"}:
            self.frustration_count += 1
        else:
            self.frustration_count = 0
        self.offtopic_count = self.offtopic_count + 1 if ext.get("in_scope") is False else 0
        return accepted

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "verified": self.verified_creator_id is not None,
            "collected_fields": sorted(self.collected.keys()),
            "remembered_intent": self.remembered_intent,
            "submission_hints": self.sub_hints,
            "active_submission_id": self.active_submission_id,
            "decision": self.review["decision"] if self.review else None,
            "emotion": self.emotion,
            "consent_status": self.consent_status,
        }

    def client_snapshot(self) -> dict[str, Any]:
        """Before verification, says nothing about which details were right."""
        snap = self.public_snapshot()
        snap["failed_verifications"] = self.failed_verifications
        if self.verified_creator_id is None:
            return {k: snap[k] for k in ("phase", "verified", "failed_verifications")}
        snap["delivery"] = self.delivery
        return snap
