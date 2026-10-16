"""Keyword reading of the reply to the email offer. Overrides a model "yes" it disagrees with."""

from __future__ import annotations

import re

_YES = re.compile(r"\b(yes|yeah|yep|yup|sure|okay|ok|go ahead|sounds good)\b", re.I)
_NO = re.compile(r"\b(no|nope|nah|skip|don'?t|do not|not now|never ?mind)\b", re.I)
_CONDITIONAL = re.compile(
    r"\b(only if|as long as|provided that|unless|but only|if my|if the)\b", re.I)
# "no rush" is not a refusal.
_BENIGN_NO = re.compile(r"\bno (rush|hurry|worries|problem|pressure)\b", re.I)
_NEGATED_AFFIRMATIVE = re.compile(r"\bnot\s+(sure|yet|really|ok|okay|yes)\b", re.I)
# "I never said yes" is a denial.
_NEGATED_PAST_CONSENT = re.compile(
    r"\b(never|didn'?t|did not|haven'?t|have not|don'?t recall|not)\s+"
    r"(said|say|agreed?|agree)\b", re.I)
# "yes, tomorrow" is not a yes.
_DEFERRED = re.compile(
    r"\b(tomorrow|later|next week|in a (bit|while|few|couple)|after(wards)?|"
    r"wait|hold off|hold on|not yet|once .* (approved|resolved|decided|confirm)|"
    r"when .* (approved|resolved|decided|confirm))\b", re.I)
_QUESTION_LEAD = re.compile(
    r"^\s*(what|how|why|when|where|who|which|can|could|would|will|is|are|do|does|did)\b",
    re.I)


def parse_consent(text: str) -> str:
    text = (text or "").strip()
    text = _BENIGN_NO.sub("", text)
    is_question = text.endswith("?") or bool(_QUESTION_LEAD.match(text))
    negated = bool(_NEGATED_AFFIRMATIVE.search(text))
    yes_hit = bool(_YES.search(text)) and not negated
    no_hit = bool(_NO.search(text)) or negated
    conditional = bool(_CONDITIONAL.search(text))
    deferred = bool(_DEFERRED.search(text))

    if _NEGATED_PAST_CONSENT.search(text):
        return "no"
    if is_question:
        return "question"
    if negated and not (_NO.search(text) or conditional or deferred):
        return "ambiguous"
    if conditional:
        return "conditional"
    if deferred:
        return "deferred"
    if yes_hit and not no_hit:
        return "yes"
    if no_hit and not yes_hit:
        return "no"
    return "ambiguous"
