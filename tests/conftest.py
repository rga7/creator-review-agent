import os

# Dummy key; no network calls.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("LLM_PROVIDER", "anthropic")

import pytest

from app import llm, metrics, ratelimit, sop
from app.state import SessionState
from app.validation import coerce_extraction, empty_extraction

class FakeLLM:
    def __init__(self):
        self._queue: list[dict] = []
        self.actions: list[dict] = []
        self.grounded: list[dict | None] = []
        self.extract_inputs: list[str] = []

    def extract(self, message, context):
        self.extract_inputs.append(message)
        raw = self._queue.pop(0) if self._queue else empty_extraction()
        clean, _ = coerce_extraction(raw)
        return clean

    def generate(self, phase, action, grounded, history, user_message):
        self.actions.append(action)
        self.grounded.append(grounded)
        return f"[{action['kind']}]"


class Chat:
    def __init__(self, fake: FakeLLM):
        self.fake, self.state = fake, SessionState("test-session")

    def say(self, message: str, **ext) -> dict:
        self.fake._queue.append({**empty_extraction(), **ext})
        sop.handle_turn(self.state, message)
        return self.fake.actions[-1]

    @property
    def grounded(self):
        return self.fake.grounded[-1]


@pytest.fixture
def fake(monkeypatch):
    f = FakeLLM()
    monkeypatch.setattr(llm, "extract", f.extract)
    monkeypatch.setattr(llm, "generate_reply", f.generate)
    return f


@pytest.fixture
def chat(fake):
    return Chat(fake)


@pytest.fixture(autouse=True)
def _clean_process_state():
    ratelimit.reset()
    metrics.reset()
    yield
    ratelimit.reset()
    metrics.reset()
