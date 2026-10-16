import pytest

from app import ratelimit


@pytest.fixture
def clock(monkeypatch):
    t = {"now": 1000.0}
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: t["now"])
    return t


def test_allows_up_to_limit_then_blocks_with_retry_after(clock):
    for _ in range(3):
        ratelimit.check("ip:1", 3, 60.0)
    with pytest.raises(ratelimit.RateLimitExceeded) as e:
        ratelimit.check("ip:1", 3, 60.0)
    assert e.value.retry_after > 0


def test_window_slides(clock):
    for _ in range(3):
        ratelimit.check("ip:1", 3, 60.0)
    clock["now"] += 61
    ratelimit.check("ip:1", 3, 60.0)


def test_keys_are_independent(clock):
    for _ in range(3):
        ratelimit.check("ip:1", 3, 60.0)
    ratelimit.check("ip:2", 3, 60.0)


def test_idle_keys_are_evicted(clock):
    ratelimit.check("ip:1", 3, 60.0)
    clock["now"] += 3600
    ratelimit.check("ip:other", 3, 60.0)  # triggers the periodic sweep
    assert "ip:1" not in ratelimit._hits
    assert "ip:1" not in ratelimit._windows


def test_blocked_reads_without_recording(clock):
    for _ in range(2):
        ratelimit.record("vfail:1", 900.0)
    assert ratelimit.blocked("vfail:1", 3, 900.0) == 0.0
    ratelimit.record("vfail:1", 900.0)
    assert ratelimit.blocked("vfail:1", 3, 900.0) > 0
    assert ratelimit.blocked("vfail:1", 3, 900.0) > 0
    clock["now"] += 901
    assert ratelimit.blocked("vfail:1", 3, 900.0) == 0.0
