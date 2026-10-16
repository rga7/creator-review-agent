import pytest

from app.state import pii_value_in_message as traced


def test_handle_traces_with_or_without_at_sign():
    assert traced("handle", "@maya.makes", "I'm maya.makes")
    assert traced("handle", "@maya.makes", "I'm @Maya.Makes")
    assert not traced("handle", "@maya.makes", "I'm someone else")


def test_phone_matches_on_digits_only():
    assert traced("phone", "+14045550142", "call me at (404) 555-0142")
    assert not traced("phone", "+14045550142", "call me at (404) 555-9999")


def test_payout_last4_exact_digits():
    assert traced("payout_last4", "7731", "payout ends in 7731")
    assert not traced("payout_last4", "7731", "payout ends in 7732")


def test_name_and_email_are_case_and_space_insensitive():
    assert traced("full_name", "Maya Okafor", "this is maya   okafor")
    assert traced("email", "maya@example.com", "it's Maya@Example.com")


@pytest.mark.parametrize("field,value", [
    ("full_name", "Maya Okafor"), ("email", "maya@example.com"), ("handle", "@maya.makes")])
def test_fabricated_values_are_rejected(field, value):
    assert not traced(field, value, "hello, I have a question about my video")


def test_empty_inputs_are_rejected():
    assert not traced("full_name", "", "anything")
    assert not traced("full_name", "Maya Okafor", "")
