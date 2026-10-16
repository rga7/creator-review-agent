import pytest

from app import data


@pytest.fixture
def reviewers(monkeypatch):
    pool = [
        {"reviewer_id": "A", "name": "A", "specialties": ["beauty"], "agreement_rate": 0.50},
        {"reviewer_id": "B", "name": "B", "specialties": ["beauty"], "agreement_rate": 0.90},
        {"reviewer_id": "C", "name": "C", "specialties": ["apps"], "agreement_rate": 0.99},
    ]
    real = data._load
    monkeypatch.setattr(data, "_load", lambda name: pool if name == "reviewers.json" else real(name))
    return pool


def test_routing_picks_the_highest_agreement_specialist_not_the_first_listed(reviewers):
    assert data.choose_reviewer("beauty")["reviewer_id"] == "B"


def test_a_specialist_beats_a_better_scoring_non_specialist(reviewers):
    assert data.choose_reviewer("apps")["reviewer_id"] == "C"
    assert data.choose_reviewer("beauty")["reviewer_id"] != "C"


def test_no_specialist_falls_back_to_the_best_overall(reviewers):
    assert data.choose_reviewer("furniture")["reviewer_id"] == "C"


def test_a_creator_only_sees_their_own_submissions():
    mine = {s["submission_id"] for s in data.submissions_for("CR-102")}
    assert mine == {"SUB-3003", "SUB-3004"}
    assert data.get_submission_for("CR-102", "SUB-3001") is None
    assert data.get_submission_for("CR-102", "sub-3003")["submission_id"] == "SUB-3003"


def test_exact_submission_id_outranks_word_matches():
    scored = data.match_submissions_scored("CR-101", ["SUB-3002", "tea"])
    assert scored[0][0]["submission_id"] == "SUB-3002" and scored[0][1] >= 100
