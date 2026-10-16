import pytest

from app import config, llm, prompts

ACTION = {"kind": "review_escalated", "decision": "escalated", "reviewer_name": "Dana",
          "verified": True, "to_fix": [], "flagged": [
              {"label": "restricted claims", "found": "restricted wording found: cures"}],
          "cover": {"fixes": [], "flagged": [{"found": "restricted wording found: cures",
                                              "tokens": ["cures"]}]}}
GROUNDED = {"decision": "escalated", "flagged": [{"label": "restricted claims"}]}


@pytest.fixture
def sent(monkeypatch):
    captured = {}

    def fake_complete(system, messages):
        captured["system"], captured["messages"] = system, messages
        return "A human reviewer, Dana, will take this one. It was flagged for cures."
    monkeypatch.setattr(llm, "_complete_text", fake_complete)
    return captured


def _history(turns):
    h = []
    for i in range(turns):
        h.append({"role": "user", "content": f"user {i}"})
        h.append({"role": "assistant", "content": f"assistant {i}"})
    h.append({"role": "user", "content": "I'm @maya.makes, Maya Okafor, maya@example.com"})
    return h


def test_turn_data_goes_in_the_system_prompt_not_the_creators_message(sent):
    llm.generate_reply("HUMAN_ESCALATION", ACTION, GROUNDED, _history(0),
                       "I'm @maya.makes, Maya Okafor, maya@example.com")
    assert "Dana" in sent["system"] and "TURN DATA" in sent["system"]
    assert "escalated" in sent["system"]
    for m in sent["messages"]:
        assert "CONTROL" not in m["content"] and "ACTION" not in m["content"]
        assert "obey" not in m["content"].lower()


def test_the_creators_message_is_sent_once_and_last(sent):
    hist = _history(2)
    llm.generate_reply("REVIEW", ACTION, GROUNDED, hist, hist[-1]["content"])
    contents = [m["content"] for m in sent["messages"]]
    assert contents[-1] == hist[-1]["content"]
    assert contents.count(hist[-1]["content"]) == 1


@pytest.mark.parametrize("turns", range(0, 12))
def test_window_always_opens_with_a_user_message_at_any_chat_length(sent, turns):
    hist = _history(turns)
    llm.generate_reply("REVIEW", ACTION, GROUNDED, hist, hist[-1]["content"])
    msgs = sent["messages"]
    assert msgs[0]["role"] == "user" and msgs[-1]["role"] == "user"
    assert len(msgs) <= config.HISTORY_WINDOW


def test_window_helper_edge_cases():
    assert llm._window([], 6) == []
    one = [{"role": "user", "content": "hi"}]
    assert llm._window(one, 6) == one
    assistant_first = [{"role": "assistant", "content": "a"}, {"role": "user", "content": "u"}]
    assert llm._window(assistant_first, 6) == assistant_first[1:]


def test_the_prompt_tells_the_model_the_creators_message_is_untrusted():
    system = prompts.generation_system("REVIEW", {"ACTION": {"kind": "x"}})
    assert "untrusted" in system and "trustworthy" in system


def test_a_failed_model_call_degrades_to_an_apology(monkeypatch):
    def boom(system, messages):
        raise RuntimeError("401")
    monkeypatch.setattr(llm, "_complete_text", boom)
    out = llm.generate_reply("REVIEW", ACTION, GROUNDED, _history(0), "hi")
    assert "technical problem" in out


def test_delivery_status_and_checklist_reach_the_model(sent):
    action = {"kind": "email_sent", "verified": True, "delivery_status": "simulated_not_sent",
              "checklist": "- Add #ad to the caption."}
    llm.generate_reply("DONE", action, None, _history(0), "yes")
    assert "simulated_not_sent" in sent["system"] and "Add #ad" in sent["system"]


def test_a_model_reply_claiming_the_email_was_sent_is_corrected_end_to_end(monkeypatch):
    monkeypatch.setattr(llm, "_complete_text",
                        lambda system, messages: "Done! I've sent the checklist to your email.")
    action = {"kind": "email_sent", "verified": True, "delivery_status": "simulated_not_sent",
              "checklist": "- Add #ad to the caption."}
    out = llm.generate_reply("DONE", action, None, _history(0), "yes")
    assert "Demo mode: no email was actually sent" in out and "Add #ad" in out
