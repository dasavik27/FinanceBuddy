"""
Concurrency tests for the tax session store.

The mutual-funds store had these; this one did not, which is precisely why it
shipped bounded-but-unlocked. Every endpoint in the tax domain is a sync `def`, so
FastAPI runs it in a threadpool and these paths are genuinely concurrent.

The specific failure being pinned: OrderedDict.move_to_end() mutates the internal
link structure, so iterating the store while another thread touches a session raises
"RuntimeError: OrderedDict mutated during iteration" - with no change in size, which
is why a naive "bounded" fix did not prevent it.

Verified by reverting the fix under a no-op lock: the original Python-level iteration
over the live dict reproduces `RuntimeError: OrderedDict mutated during iteration`
reliably here. Worth being precise about which half does what, because it matters if
someone refactors these functions later:

  - Snapshotting under the lock (`list(_tax_sessions.items())` then iterate) is what
    removes the RuntimeError from the *read* paths. A bare `list()` is a single
    C-level operation, so it cannot be interrupted mid-iteration the way a Python
    `for` loop can - which means restoring direct iteration would reintroduce the bug
    even with the lock held by other callers.
  - The lock is what protects the *read-modify-write* sequences: the cold-start
    check-then-act, evict-after-insert, and the persist snapshot. Those fail as lost
    sessions and lost updates rather than as exceptions, which is why they need their
    own tests below rather than just an absence of raises.
"""

import threading


def _as_user(subject, fn):
    """Run fn as an authenticated user.

    create_tax_session() takes its owner from the identity scope rather than a
    keyword now: the owner must be the authenticated caller, and a parameter is
    something a request could otherwise assert for itself.

    Resolves a real backing account for `subject` rather than fabricating a Caller
    with an arbitrary string: `sessions.user_id` is a uuid with a foreign key to
    `users(id)`, so an unresolved id fails at the database - a persist error deep in
    a background thread - rather than surfacing where the mistake actually is.
    """
    from shared import identity, users
    from tests.conftest import TEST_ISSUER
    caller = users.resolve(TEST_ISSUER, str(subject))
    with identity.identity_scope(caller):
        return fn()


import pytest

from domains.tax_expert import tax_sessions

from tests.conftest import requires_db

# Postgres replaced SQLite, so these need a real server. Skipped with a reason rather
# than failing with a connection error when TEST_DATABASE_URL is unset - see
# tests/conftest.py.
pytestmark = requires_db



@pytest.fixture(autouse=True)
def small_store(monkeypatch, clean_db):
    """
    A tight cap so eviction runs constantly during the test.

    Depends on clean_db (not just requires_db) so every test in this module runs
    against the throwaway schema: without it, DATABASE_URL is whatever is already in
    the environment - the production DSN on a developer machine - since nothing else
    in this file would otherwise redirect it.
    """
    monkeypatch.setattr(tax_sessions, "MAX_SESSIONS", 4)
    yield
    tax_sessions.clear_all()


def _ais(tag: str) -> dict:
    return {"personal": {"pan": tag}, "fy": "2025-26", "salary": {"gross": 100000}}


def test_concurrent_create_and_iterate_does_not_raise():
    """
    Writers inserting (and evicting) while readers iterate the store.

    Against the unlocked version this raises RuntimeError from list_sessions() or
    get_sessions_by_pan() - the reachable 500 whenever /accounts/summary overlapped
    any tax request.
    """
    errors = []
    stop = threading.Event()
    created = []
    created_lock = threading.Lock()

    def writer(n):
        try:
            for i in range(25):
                sid = _as_user(f"W{n}I{i}", lambda: tax_sessions.create_tax_session(_ais(f"W{n}I{i}")))
                with created_lock:
                    created.append(sid)
        except Exception as exc:  # pragma: no cover - the bug being pinned
            errors.append(("writer", exc))
        finally:
            stop.set()

    def reader():
        try:
            while not stop.is_set():
                tax_sessions.list_sessions()
                tax_sessions.get_sessions_by_pan("W0I0")
                with created_lock:
                    snapshot = list(created)
                for sid in snapshot[-3:]:
                    tax_sessions.get_tax_session(sid)  # calls move_to_end
        except Exception as exc:  # pragma: no cover - the bug being pinned
            errors.append(("reader", exc))

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(3)]
    threads += [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"concurrent access raised: {errors}"
    assert len(tax_sessions.list_sessions()) <= tax_sessions.MAX_SESSIONS


def test_concurrent_first_access_does_not_lose_a_session():
    """
    Two threads racing the cold-start load must not discard each other's work.

    _load_from_disk() used to rebind the module global to a fresh OrderedDict, so the
    loser's reassignment threw away a session the winner had just inserted. The store
    now clears in place under the lock.
    """
    sid = _as_user("RACER1", lambda: tax_sessions.create_tax_session(_ais("RACER1")))

    # Force the cold-start path: flag cleared, store emptied, row still on disk.
    tax_sessions.clear_all()

    errors = []
    results = []
    barrier = threading.Barrier(6)

    def racer():
        try:
            barrier.wait(timeout=10)
            results.append(tax_sessions.get_tax_session(sid))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=racer) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent cold start raised: {errors}"
    assert all(r is not None for r in results), "a concurrent cold start lost the session"
    # Every caller must hold the *same* dict, or mutations through one are invisible
    # to the other.
    assert len({id(r) for r in results}) == 1, "callers received divergent session objects"

    tax_sessions.delete_tax_session(sid)


def test_editing_an_evicted_session_persists():
    """
    Editing a session that is no longer resident must still write to disk.

    Honest scope note: this covers the *single-threaded* path — evicted, then edited,
    then re-read — which works because _rehydrate() re-inserts before _mutate applies.
    It does NOT reproduce the concurrent window _mutate guards against (another thread
    evicting between the rehydrate and the second lock acquisition, after which
    _persist_one would look up a missing id and silently skip the write). I verified
    that by removing the guard: this test still passes without it.

    The guard is kept because the race is real and the cost is one dict assignment,
    but it is not covered by a test — reproducing it needs deterministic control over
    thread interleaving that is not worth the fixture complexity here.
    """
    monkey_cap = 2
    original = tax_sessions.MAX_SESSIONS
    tax_sessions.MAX_SESSIONS = monkey_cap
    try:
        sid = _as_user("SURVIVE", lambda: tax_sessions.create_tax_session(_ais("SURVIVE")))

        # Push it out of the resident set entirely.
        filler = [
            _as_user(f"FILL{i}", lambda: tax_sessions.create_tax_session(_ais(f"FILL{i}")))
            for i in range(4)
        ]
        assert sid not in {s for s, _ in tax_sessions.list_sessions()}

        # Now edit the evicted session, with more eviction pressure applied around it.
        assert tax_sessions.update_deductions(sid, {"80C": 150000}) is True

        for i in range(4):
            _as_user(f"MORE{i}", lambda: tax_sessions.create_tax_session(_ais(f"MORE{i}")))
            filler.append(_ais(f"MORE{i}"))

        # Re-read from disk: the deduction must have persisted.
        tax_sessions.clear_all()
        restored = tax_sessions.get_tax_session(sid)
        assert restored is not None, "session lost entirely"
        assert restored["deductions"] == {"80C": 150000}, (
            f"edit was silently discarded: {restored.get('deductions')}"
        )
    finally:
        tax_sessions.MAX_SESSIONS = original
        tax_sessions.clear_all()


def test_concurrent_mutation_and_persist_does_not_raise():
    """
    json.dumps used to serialize the live session dict, so a concurrent mutation
    could raise "dictionary changed size during iteration" from the persist path.
    """
    sid = _as_user("MUTATE", lambda: tax_sessions.create_tax_session(_ais("MUTATE")))
    errors = []
    stop = threading.Event()

    def mutator(n):
        try:
            for i in range(40):
                tax_sessions.update_overrides(sid, {f"key_{n}_{i}": {"v": i}})
        except Exception as exc:  # pragma: no cover
            errors.append(("mutator", exc))
        finally:
            stop.set()

    def deducer():
        try:
            while not stop.is_set():
                tax_sessions.update_deductions(sid, {"80C": 150000})
                tax_sessions.get_session_version(sid)
        except Exception as exc:  # pragma: no cover
            errors.append(("deducer", exc))

    threads = [threading.Thread(target=mutator, args=(n,)) for n in range(3)]
    threads.append(threading.Thread(target=deducer))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"concurrent mutation raised: {errors}"
    tax_sessions.delete_tax_session(sid)
