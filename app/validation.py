"""Coerces model output to the extraction schema and reports what it had to fix."""

from __future__ import annotations

import re
from typing import Any

PII_KEYS = ("handle", "creator_id", "full_name", "email", "payout_last4", "phone")
INTENTS = {"review", "other_submission"}
EMOTIONS = {"neutral", "frustrated", "angry", "anxious", "confused"}
CONSENT_VALUES = {"grant", "deny", "conditional", "defer", "unclear"}
BOOL_FLAGS = ("wants_human", "in_scope", "conversation_wrapup")
BOOL_DEFAULTS = {"in_scope": True}

_CONTROL_MARKER = re.compile(r"\[\s*control\b[^\]]*\]", re.I)
_MESSAGE_MARKER = re.compile(r"\bCREATOR MESSAGE\s*:", re.I)


def sanitize_control_injection(text: str) -> str:
    if not text:
        return text
    text = _CONTROL_MARKER.sub("[reference removed]", text)
    return _MESSAGE_MARKER.sub("creator message ref:", text)


def empty_extraction() -> dict:
    return {"pii": {}, "intent": None, "submission_hints": [], "emotion": "neutral",
            "wants_human": False, "in_scope": True,
            "conversation_wrapup": False, "email_consent": None}


def _as_bool(value: Any, default: bool, issues: list[str], key: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        issues.append(f"{key}_was_str")
        return value.strip().lower() in ("true", "yes", "1", "y")
    if isinstance(value, (int, float)):
        issues.append(f"{key}_was_number")
        return bool(value)
    issues.append(f"{key}_bad_type")
    return default


def coerce_extraction(raw: Any) -> tuple[dict, list[str]]:
    issues: list[str] = []
    if not isinstance(raw, dict):
        return empty_extraction(), ["not_a_dict"]
    out = empty_extraction()

    pii = raw.get("pii")
    if pii is None:
        pii = {}
    elif not isinstance(pii, dict):
        issues.append("pii_not_dict")
        pii = {}
    for k, v in pii.items():
        if k not in PII_KEYS:
            issues.append("pii_unknown_key")
        elif isinstance(v, str) and v.strip():
            out["pii"][k] = v.strip()
        elif v not in (None, ""):
            issues.append(f"pii.{k}_bad_type")

    intent = raw.get("intent")
    if intent is not None and (not isinstance(intent, str) or intent not in INTENTS):
        issues.append("intent_out_of_enum")
        intent = None
    out["intent"] = intent

    hints = raw.get("submission_hints")
    if isinstance(hints, str):
        issues.append("submission_hints_was_str")
        hints = [hints]
    elif hints is None:
        hints = []
    elif not isinstance(hints, list):
        issues.append("submission_hints_not_list")
        hints = []
    out["submission_hints"] = [h.strip() for h in hints if isinstance(h, str) and h.strip()]

    emotion = raw.get("emotion")
    if not isinstance(emotion, str) or emotion not in EMOTIONS:
        if emotion is not None:
            issues.append("emotion_out_of_enum")
        emotion = "neutral"
    out["emotion"] = emotion

    for key in BOOL_FLAGS:
        out[key] = _as_bool(raw.get(key), BOOL_DEFAULTS.get(key, False), issues, key)

    consent = raw.get("email_consent")
    if consent is not None and (not isinstance(consent, str) or consent not in CONSENT_VALUES):
        issues.append("email_consent_out_of_enum")
        consent = None
    out["email_consent"] = consent
    return out, issues
