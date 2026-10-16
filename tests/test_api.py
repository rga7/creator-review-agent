import pytest
from fastapi.testclient import TestClient

from app import config, main


@pytest.fixture
def client(fake):
    main._STORE._items.clear()
    with TestClient(main.app) as c:
        yield c


def _post(client, message="hi", session_id=None):
    return client.post("/chat", json={"session_id": session_id, "message": message})


def test_health_reports_provider_and_session_count(client):
    body = client.get("/health").json()
    assert body["ok"] and body["provider"] == "anthropic" and body["sessions"] == 0


def test_chat_issues_a_session_and_keeps_it(client):
    first = _post(client).json()
    second = _post(client, session_id=first["session_id"]).json()
    assert second["session_id"] == first["session_id"]
    assert first["phase"] == "VERIFY_ID" and first["verified"] is False


def test_an_id_the_server_did_not_issue_gets_a_fresh_session(client):
    body = _post(client, session_id="guessed-or-expired-id").json()
    assert body["session_id"] != "guessed-or-expired-id"


def test_overlong_message_is_rejected(client):
    assert _post(client, message="x" * 2001).status_code == 422


def test_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(config, "IP_RATE_LIMIT", (2, 60.0))
    assert _post(client).status_code == 200
    assert _post(client).status_code == 200
    r = _post(client)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


def test_failed_identity_attempts_lock_the_address_out(client, fake, monkeypatch):
    monkeypatch.setattr(config, "IP_VERIFY_FAIL_LIMIT", (2, 900.0))
    monkeypatch.setattr(config, "MAX_VERIFY_FAILURES", 99)  # isolate the per-IP limit

    def wrong(n):
        fake._queue.append({"pii": {"handle": "@maya.makes", "full_name": "Maya Okafor",
                                    "email": f"wrong{n}@example.com"}})
        return _post(client, f"@maya.makes Maya Okafor wrong{n}@example.com")

    assert wrong(1).status_code == 200
    assert wrong(2).status_code == 200
    r = wrong(3)
    assert r.status_code == 429 and "failed identity" in r.json()["detail"].lower()


def test_review_result_reaches_the_browser_without_internal_fields(client, fake):
    fake._queue.append({"pii": {"handle": "@maya.makes", "full_name": "Maya Okafor",
                                "email": "maya@example.com"},
                        "submission_hints": ["SUB-3001"]})
    body = _post(client, "I'm @maya.makes, Maya Okafor, maya@example.com, SUB-3001").json()
    review = body["memory"]["review"]
    assert body["verified"] and review["decision"] == "changes_requested"
    assert all("must_mention" not in item for item in review["to_fix"])


def test_reset_drops_the_session(client):
    sid = _post(client).json()["session_id"]
    client.post("/reset", json={"session_id": sid})
    assert main._STORE.get(sid) is None


def test_startup_refuses_to_run_without_a_provider_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    with pytest.raises(RuntimeError, match="No AI model configured"):
        config.validate()
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(config, "API_KEY", "")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        config.validate()
