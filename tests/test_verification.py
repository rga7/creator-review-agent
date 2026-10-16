from app import verification
from app.state import SessionState


def _state(**collected):
    s = SessionState("t")
    s.collected = collected
    return s


def test_two_details_with_one_private_verifies():
    s = _state(handle="@maya.makes", full_name="Maya Okafor", email="maya@example.com")
    ok, info = verification.try_verify(s)
    assert ok and s.verified_creator_id == "CR-101"
    assert info["matched"] == ["full_name", "email"]


def test_name_alone_never_verifies_even_with_locator():
    s = _state(handle="@maya.makes", full_name="Maya Okafor")
    ok, _ = verification.try_verify(s)
    assert not ok and s.verified_creator_id is None


def test_one_private_detail_is_not_enough():
    ok, _ = verification.try_verify(_state(handle="@maya.makes", email="maya@example.com"))
    assert not ok


def test_two_private_details_verify_without_a_name():
    ok, _ = verification.try_verify(
        _state(handle="@maya.makes", email="maya@example.com", payout_last4="7731"))
    assert ok


def test_details_without_a_locator_never_verify():
    ok, info = verification.try_verify(
        _state(full_name="Maya Okafor", email="maya@example.com", payout_last4="7731"))
    assert not ok and info["reason"] == "no_record"


def test_creator_id_works_as_a_locator():
    ok, _ = verification.try_verify(
        _state(creator_id="cr-101", email="maya@example.com", phone="(404) 555-0142"))
    assert ok


def test_one_wrong_detail_among_correct_ones_still_counts_only_the_right_ones():
    ok, info = verification.try_verify(
        _state(handle="@maya.makes", email="maya@example.com", payout_last4="0000"))
    assert not ok and info["matched"] == ["email"]


def test_details_of_another_creator_do_not_verify():
    # Leo's details, Maya's handle.
    ok, _ = verification.try_verify(
        _state(handle="@maya.makes", email="leo@example.com", payout_last4="2209"))
    assert not ok
