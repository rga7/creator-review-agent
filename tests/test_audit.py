import json
import logging

import pytest

from app import audit
from tests.helpers import MAYA, MAYA_PII


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


@pytest.fixture
def captured():
    handler = Capture()
    audit.audit_log.addHandler(handler)
    yield handler
    audit.audit_log.removeHandler(handler)


def test_audit_events_are_emitted_by_default():
    assert audit.audit_log.isEnabledFor(logging.INFO)
    assert audit.audit_log.handlers


def test_events_are_json_with_event_and_session(captured):
    audit.human_escalation("s1", "explicit_request")
    event = json.loads(captured.lines[0])
    assert event["event"] == "human_escalation" and event["session_id"] == "s1"


def test_a_full_verification_logs_outcomes_but_never_the_details(chat, captured):
    chat.say(MAYA + " SUB-3001", pii=MAYA_PII, submission_hints=["SUB-3001"])
    text = "\n".join(captured.lines)
    assert "verification_attempt" in text and "review_decision" in text
    for secret in ("maya@example.com", "Maya Okafor", "7731"):
        assert secret not in text
