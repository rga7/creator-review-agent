from __future__ import annotations

import json
import logging
import re

from . import config, metrics, prompts
from .validation import coerce_extraction, empty_extraction

log = logging.getLogger("sop.llm")
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if config.LLM_PROVIDER == "anthropic":
        import anthropic
        _client = anthropic.Anthropic(api_key=config.API_KEY, timeout=config.LLM_TIMEOUT_S,
                                      max_retries=config.LLM_MAX_RETRIES)
    elif config.LLM_PROVIDER == "openai":
        import openai
        _client = openai.OpenAI(api_key=config.API_KEY, timeout=config.LLM_TIMEOUT_S,
                                max_retries=config.LLM_MAX_RETRIES)
    else:
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {config.LLM_PROVIDER!r}")
    return _client


def _parse_json_block(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)


def _trim_to_last_sentence(text: str) -> str:
    ends = [m.end() for m in re.finditer(r"[.!?](?:\s|$)", text)]
    return text[:ends[-1]].rstrip() if ends else text


def _complete_text_raw(system: str, messages: list[dict], max_tokens: int) -> tuple[str, bool]:
    client = _get_client()
    if config.LLM_PROVIDER == "anthropic":
        msg = client.messages.create(model=config.LLM_MODEL, max_tokens=max_tokens,
                                     system=system, messages=messages)
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return text, msg.stop_reason == "max_tokens"
    resp = client.chat.completions.create(
        model=config.LLM_MODEL, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}] + messages)
    choice = resp.choices[0]
    return (choice.message.content or "").strip(), choice.finish_reason == "length"


def _complete_json(system: str, user: str) -> dict:
    text, _ = _complete_text_raw(system, [{"role": "user", "content": user}],
                                 config.EXTRACTION_MAX_TOKENS)
    try:
        return _parse_json_block(text)
    except (json.JSONDecodeError, ValueError):
        metrics.incr("extraction_repaired")
        retry, _ = _complete_text_raw(system, [
            {"role": "user", "content": user},
            {"role": "assistant", "content": text},
            {"role": "user", "content": "That was not valid JSON. Reply with ONLY the "
                                        "JSON object described, no prose, no code fences."},
        ], config.EXTRACTION_MAX_TOKENS)
        return _parse_json_block(retry)


def _complete_text(system: str, messages: list[dict]) -> str:
    text, truncated = _complete_text_raw(system, messages, config.GENERATION_MAX_TOKENS)
    if truncated:
        metrics.incr("generation_truncated")
        text = _trim_to_last_sentence(text)
    return text


def extract(message: str, context: dict) -> dict:
    metrics.incr("extraction_total")
    user = f"CONTEXT: {json.dumps(context)}\n\nCREATOR MESSAGE: {message}"
    try:
        raw = _complete_json(prompts.EXTRACTION_SYSTEM, user)
        metrics.incr("extraction_json_ok")
    except Exception as e:
        # A failed call falls back to an empty extraction, which cannot verify or decide.
        metrics.incr("extraction_fallback")
        log.warning("extraction failed, using empty extraction: %s", e)
        return empty_extraction()
    clean, issues = coerce_extraction(raw)
    for issue in issues:
        metrics.incr(f"extraction_issue:{issue}")
    if issues:
        metrics.incr("extraction_coerced")
    return clean


_DECISION_LINE = {
    "approved": "Good news: this submission is approved.",
    "changes_requested": "This submission needs a few changes before it can be approved.",
    "escalated": "A human reviewer needs to take a look at this submission.",
}
_NEGATED_CHANGES = re.compile(
    r"\b(no|any|without|zero)\s+(further |more |other )?(changes?|fix(es)?|updates?|edits?)\b")
_NEGATED_APPROVAL = re.compile(
    r"\b(not|n't|cannot|can't|isn't|without)\b[^.\n]{0,25}\bapproved\b"
    r"|\bbefore (it|this) can be approved\b")
_CHANGES = re.compile(
    r"\b(needs?|requires?|request(ed|ing)?)\b[^.\n]{0,40}\b(changes?|fix(es)?|updates?|edits?|revis\w+)\b"
    r"|\bchanges? (are |is )?(needed|requested|required)\b"
    r"|\bneeds? to (change|be (fixed|updated|revised))\b")
_ESCALATED = re.compile(r"\b(human|reviewer|person on (our|the) team)\b")


def states_decision(decision: str, reply: str) -> bool:
    low = reply.lower()
    if decision == "approved":
        return "approved" in low and not _NEGATED_APPROVAL.search(low)
    if decision == "changes_requested":
        return bool(_CHANGES.search(_NEGATED_CHANGES.sub("", low)))
    if decision == "escalated":
        return bool(_ESCALATED.search(low))
    return True


def ensure_decision(action: dict, reply: str) -> str:
    """Appends what the reply left out. Cannot remove a sentence that contradicts the decision."""
    if action.get("kind") not in ("review_result", "review_escalated"):
        return reply
    decision = action.get("decision")
    if decision in _DECISION_LINE and not states_decision(decision, reply):
        reply = f"{_DECISION_LINE[decision]}\n\n{reply}"
    low = reply.lower()
    cover = action.get("cover") or {}

    missing = [f for f in cover.get("fixes", [])
               if not any(t.lower() in low for t in f["tokens"])]
    if missing:
        metrics.incr("backstop_added_fixes")
        reply += "\n\nStill to fix:\n" + "\n".join(f"- {m['fix']}" for m in missing)

    extra = []
    name = action.get("reviewer_name")
    if name and name.lower() not in low:
        extra.append(f"{name} will take this one.")
    for item in cover.get("flagged", []):
        if item["tokens"] and not any(t.lower() in low for t in item["tokens"]):
            extra.append(f"Flagged: {item['found']}.")
    if extra:
        metrics.incr("backstop_added_escalation_facts")
        reply += "\n\n" + " ".join(extra)
    return reply


def ensure_delivery_note(action: dict, reply: str) -> str:
    if action.get("kind") == "email_sent" and \
            action.get("delivery_status") == "simulated_not_sent" and \
            "demo" not in reply.lower():
        metrics.incr("backstop_added_demo_note")
        reply += ("\n\n(Demo mode: no email was actually sent. Here is the checklist "
                  f"instead:)\n\n{action.get('checklist', '')}")
    return reply


def _window(history: list[dict], n: int) -> list[dict]:
    """Anthropic's API rejects a conversation that starts with an assistant message."""
    window = history[-n:]
    while window and window[0]["role"] != "user":
        window = window[1:]
    return window


def generate_reply(phase: str, action: dict, grounded: dict | None,
                   history: list[dict], user_message: str) -> str:
    kind = action.get("kind", "")
    control = {
        "ACTION": {k: v for k, v in action.items() if k not in ("to_fix", "flagged", "cover", "checklist")},
        "INSTRUCTION": prompts.KIND_INSTRUCTIONS.get(kind, ""),
        "GROUNDED_DATA": grounded,
        "ASK_FOR": action.get("ask_for"),
        "CANDIDATES": action.get("candidates"),
        "TO_FIX": [{"fix": i["fix"], "label": i["label"]} for i in action.get("to_fix", [])],
        "FLAGGED": action.get("flagged", []),
        "REVIEWER": action.get("reviewer_name"),
        "REVISION_LIMIT_REACHED": action.get("revision_limit_reached", False),
        "DELIVERY_STATUS": action.get("delivery_status"),
        "CHECKLIST": action.get("checklist"),
    }
    # In the system prompt: inside the user message the model treated it as an injection.
    system = prompts.generation_system(phase, control)
    try:
        reply = _complete_text(system, _window(history, config.HISTORY_WINDOW))
        return ensure_delivery_note(action, ensure_decision(action, reply))
    except Exception as e:
        metrics.incr("generation_error")
        log.warning("generation failed: %s", e)
        return ("I'm sorry, I'm having a brief technical problem on my end. "
                "Could you say that again in a moment?")
