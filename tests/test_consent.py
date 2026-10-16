import pytest

from app.consent import parse_consent


@pytest.mark.parametrize("msg,expected", [
    ("yes", "yes"), ("Sure, go ahead", "yes"), ("yes please", "yes"),
    ("no thanks", "no"), ("skip it", "no"),
    ("I never said yes", "no"), ("I didn't agree to that", "no"),
    ("not sure", "ambiguous"), ("not yet", "deferred"),
    ("yes, send it tomorrow", "deferred"),
    ("sure, but wait for my confirmation", "deferred"),
    ("yes but only if my video is approved", "conditional"),
    ("what happens now?", "question"),
    ("is saying yes enough to send it?", "question"),
    ("", "ambiguous"),
])
def test_consent_reading(msg, expected):
    assert parse_consent(msg) == expected


def test_mixed_signals_fail_safe_to_ambiguous():
    assert parse_consent("yes, and don't forget the second video") == "ambiguous"


@pytest.mark.parametrize("msg", [
    "yes send it, no rush", "yes, no hurry", "sure, no problem", "yes please, no pressure",
])
def test_polite_no_pressure_phrases_do_not_cancel_a_yes(msg):
    assert parse_consent(msg) == "yes"


def test_a_real_no_after_a_polite_phrase_is_still_a_no():
    assert parse_consent("no rush, but no thanks") == "no"
