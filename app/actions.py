"""The actions the agent can take on a turn. Each needs an entry in prompts.KIND_INSTRUCTIONS."""

from enum import Enum


class Kind(str, Enum):
    NEED_MORE_DETAILS = "need_more_details"
    VERIFIED = "verified"
    VERIFY_LOCKOUT = "verify_lockout"
    RESOLVE_NEED_CLARIFY = "resolve_need_clarify"
    RESOLVE_AMBIGUOUS = "resolve_ambiguous"
    RESOLVE_UNKNOWN_ID = "resolve_unknown_id"
    REVIEW_RESULT = "review_result"
    REVIEW_ESCALATED = "review_escalated"
    REVIEW_FOLLOWUP = "review_followup"
    ESCALATED_FOLLOWUP = "escalated_followup"
    OFFER_EMAIL = "offer_email"
    EMAIL_SENT = "email_sent"
    EMAIL_SKIPPED = "email_skipped"
    EMAIL_CONDITIONAL = "email_conditional"
    EMAIL_DEFERRED = "email_deferred"
    EMAIL_FAILED = "email_failed"
    CLOSING = "closing"
    DONE = "done"
    OFFTOPIC = "offtopic"
    OFFTOPIC_HUMAN = "offtopic_human"
    HUMAN = "human"

    def __str__(self) -> str:
        return self.value
