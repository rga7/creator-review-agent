import copy

import pytest

from app import checks, data


def _sub(sid):
    return copy.deepcopy(next(s for s in data._load("submissions.json")
                              if s["submission_id"] == sid))


def _run(sid, **overrides):
    sub = _sub(sid)
    sub.update(overrides)
    brief = data.get_brief(sub["campaign_id"])
    results = checks.run_checks(brief, sub)
    return sub, results, checks.decide(results, sub)


def _failed(results):
    return {r.id for r in results if not r.passed}


def test_clean_submission_is_approved():
    _, results, decision = _run("SUB-3003")
    assert decision["decision"] == "approved"
    assert not _failed(results)


def test_fixable_failures_request_changes():
    _, results, decision = _run("SUB-3001")
    assert _failed(results) == {"duration", "disclosure"}
    assert decision["decision"] == "changes_requested"


# The tea brief allows 15-45s.
@pytest.mark.parametrize("duration,ok", [(14, False), (15, True), (45, True), (46, False)])
def test_duration_bounds_are_inclusive(duration, ok):
    sub = _sub("SUB-3001")
    sub["duration_s"] = duration
    r = next(x for x in checks.run_checks(data.get_brief("CAMP-TEA"), sub) if x.id == "duration")
    assert r.passed is ok


def test_wrong_aspect_ratio_fails():
    _, results, _ = _run("SUB-3003", aspect_ratio="16:9")
    assert "aspect_ratio" in _failed(results)


def test_either_disclosure_tag_is_accepted():
    _, results, _ = _run("SUB-3003", hashtags=["#sponsored", "#strideupstreak"])
    assert "disclosure" not in _failed(results)


def test_missing_required_hashtag_and_mention_fail():
    _, results, _ = _run("SUB-3003", hashtags=["#ad"], mentions=[])
    assert {"hashtag:#strideupstreak", "mention:@strideupapp"} <= _failed(results)


def test_tags_are_case_insensitive():
    _, results, _ = _run("SUB-3003", hashtags=["#AD", "#StrideUpStreak"], mentions=["@StrideUpApp"])
    assert not _failed(results)


def test_talking_point_needs_one_keyword_in_transcript_or_caption():
    _, results, _ = _run("SUB-3003", transcript="Nice walk today.", caption="#ad")
    assert "point:streak" in _failed(results)
    _, results, _ = _run("SUB-3003", transcript="Nice walk today.", caption="my streak #ad")
    assert "point:streak" not in _failed(results)


def test_banned_phrase_is_a_blocker_and_escalates():
    _, results, decision = _run("SUB-3002")
    assert _failed(results) == {"banned_claims"}
    assert decision["decision"] == "escalated"
    assert decision["reason"] == "blocker:banned_claims"


def test_banned_phrase_matches_whole_words_only():
    # "secures" contains "cures".
    _, results, _ = _run("SUB-3002", transcript="The texture is silky and it secures my routine.")
    assert "banned_claims" not in _failed(results)


def test_blocker_wins_over_fixable_failures():
    _, _, decision = _run("SUB-3002", duration_s=200, hashtags=[])
    assert decision["decision"] == "escalated" and decision["reason"].startswith("blocker")


def test_originality_flag_escalates():
    _, _, decision = _run("SUB-3005")
    assert decision["decision"] == "escalated" and decision["reason"] == "blocker:originality"


def test_revision_limit_escalates_instead_of_looping():
    _, _, decision = _run("SUB-3004")
    assert decision["decision"] == "escalated" and decision["reason"] == "revision_limit"


def test_revision_limit_does_not_block_an_approval():
    _, _, decision = _run("SUB-3003", revision_count=5)
    assert decision["decision"] == "approved"


def test_creator_view_hides_the_originality_check():
    _, _, decision = _run("SUB-3005")
    view = checks.creator_view(decision)
    assert view["flagged"] == []
    assert "originality" not in str(view).lower()


def test_creator_view_shows_restricted_wording():
    _, _, decision = _run("SUB-3002")
    view = checks.creator_view(decision)
    assert "cures" in view["flagged"][0]["found"]


def test_creator_view_splits_fixes_from_passes():
    _, _, decision = _run("SUB-3001")
    view = checks.creator_view(decision)
    assert {i["label"] for i in view["to_fix"]} == {"video length", "paid-partnership disclosure"}
    assert "aspect ratio" in view["passed"]


def test_creator_view_carries_no_backstop_tokens():
    _, _, decision = _run("SUB-3001")
    assert "must_mention" not in str(checks.creator_view(decision))


def test_reply_must_cover_lists_visible_failures_only():
    _, _, decision = _run("SUB-3001")
    cover = checks.reply_must_cover(decision)
    assert {f["fix"] for f in cover["fixes"]} == {
        i["fix"] for i in checks.creator_view(decision)["to_fix"]}
    _, _, hidden = _run("SUB-3005")
    assert checks.reply_must_cover(hidden) == {"fixes": [], "flagged": []}
