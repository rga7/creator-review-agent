import pytest

from app import llm

FIXES = {
    "fixes": [
        {"fix": "Trim the video to between 15 and 45 seconds.", "tokens": ["45", "15"]},
        {"fix": "Add #ad to the caption.", "tokens": ["#ad", "#sponsored"]},
    ],
    "flagged": [],
}


def _action(decision="changes_requested", cover=None, kind="review_result", **extra):
    return {"kind": kind, "decision": decision, "cover": cover or {"fixes": [], "flagged": []},
            **extra}


@pytest.mark.parametrize("decision,reply,expected", [
    ("changes_requested", "It needs changes before it can be approved", True),
    ("changes_requested", "The decision is changes requested", True),
    ("changes_requested", "No changes needed, looks great", False),
    ("changes_requested", "Your video is unchanged", False),
    ("approved", "Approved!", True),
    ("approved", "I cannot approve that", False),
    ("approved", "It is not approved yet", False),
    ("approved", "This needs changes before it can be approved", False),
    ("escalated", "A human reviewer will take this one", True),
    ("escalated", "Thanks for your patience", False),
])
def test_states_decision(decision, reply, expected):
    assert llm.states_decision(decision, reply) is expected


def test_a_good_reply_is_left_alone():
    reply = "This needs changes: trim it to 45 seconds and add #ad."
    assert llm.ensure_decision(_action(cover=FIXES), reply) == reply


def test_missing_decision_is_prepended():
    out = llm.ensure_decision(_action("approved"), "Here is how it went.")
    assert out.startswith("Good news: this submission is approved.")


def test_a_reply_that_says_no_changes_needed_still_gets_the_real_decision():
    out = llm.ensure_decision(_action(cover=FIXES), "No changes needed, looks great. 45 #ad")
    assert out.startswith("This submission needs a few changes")


def test_missing_fixes_are_appended_once_each():
    out = llm.ensure_decision(_action(cover=FIXES), "Some changes are needed. Trim to 45 seconds.")
    assert "Add #ad to the caption." in out
    assert "Trim the video to between 15 and 45 seconds." not in out


def test_other_kinds_are_untouched():
    assert llm.ensure_decision({"kind": "offer_email"}, "hi") == "hi"


ESCALATION = _action(
    "escalated", kind="review_escalated", reviewer_name="Dana",
    cover={"fixes": [], "flagged": [{"found": "restricted wording found: cures",
                                     "tokens": ["cures"]}]})


def test_escalation_without_the_reviewer_name_gets_it_added():
    out = llm.ensure_decision(ESCALATION, "A human reviewer will look. It was flagged for cures.")
    assert "Dana will take this one." in out


def test_escalation_without_the_flagged_wording_gets_it_added():
    out = llm.ensure_decision(ESCALATION, "A human reviewer, Dana, will take this one.")
    assert "Flagged: restricted wording found: cures." in out


def test_a_complete_escalation_reply_is_left_alone():
    reply = "A human reviewer, Dana, will take this one. It was flagged for cures."
    assert llm.ensure_decision(ESCALATION, reply) == reply


def test_nothing_is_added_for_a_hidden_flag():
    action = {**ESCALATION, "cover": {"fixes": [], "flagged": []}}
    reply = "A human reviewer, Dana, will take this one."
    assert llm.ensure_decision(action, reply) == reply


SENT = {"kind": "email_sent", "delivery_status": "simulated_not_sent",
        "checklist": "- Add #ad to the caption."}


def test_demo_delivery_that_claims_it_was_sent_gets_corrected():
    out = llm.ensure_delivery_note(SENT, "Done, I've sent the checklist to your email.")
    assert "Demo mode: no email was actually sent" in out and "Add #ad" in out


def test_a_reply_that_already_says_it_is_a_demo_is_left_alone():
    reply = "This is a demo, so nothing was emailed. Here it is: - Add #ad."
    assert llm.ensure_delivery_note(SENT, reply) == reply


def test_real_delivery_is_not_given_a_demo_note():
    assert llm.ensure_delivery_note({**SENT, "delivery_status": "sent"}, "Sent!") == "Sent!"
