from app.sessions import SessionStore


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now


def test_unknown_or_missing_id_returns_none():
    store = SessionStore(60, 10, Clock())
    assert store.get("nope") is None
    assert store.get(None) is None


def test_created_session_is_found_and_has_server_issued_id():
    store = SessionStore(60, 10, Clock())
    st = store.create()
    assert store.get(st.session_id) is st
    assert len(st.session_id) == 32


def test_idle_session_expires():
    clock = Clock()
    store = SessionStore(60, 10, clock)
    st = store.create()
    clock.now = 61
    assert store.get(st.session_id) is None
    assert len(store) == 0


def test_activity_keeps_a_session_alive():
    clock = Clock()
    store = SessionStore(60, 10, clock)
    st = store.create()
    for t in (50, 100, 150):
        clock.now = t
        assert store.get(st.session_id) is st


def test_cap_evicts_the_least_recently_used():
    clock = Clock()
    store = SessionStore(1000, 2, clock)
    a = store.create(); clock.now = 1
    b = store.create(); clock.now = 2
    store.get(a.session_id); clock.now = 3  # a is fresher than b
    c = store.create()
    assert len(store) == 2
    assert store.get(b.session_id) is None
    assert store.get(a.session_id) is a and store.get(c.session_id) is c


def test_drop_removes_session():
    store = SessionStore(60, 10, Clock())
    st = store.create()
    store.drop(st.session_id)
    assert store.get(st.session_id) is None
