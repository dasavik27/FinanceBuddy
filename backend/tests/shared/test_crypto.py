"""
Column encryption.

No database needed, which is the point: this is the one genuinely new piece of
security logic in the durable-storage work, so it is tested for real rather than
deferred behind TEST_DATABASE_URL like the persistence tests.

Every rejection case here is a property the storage layer relies on. The
transplant test in particular covers an attack that encryption alone does not
prevent - it needs the associated-data binding.
"""

import base64
import os

import pytest

from shared import crypto


def _key(seed: int = 1) -> str:
    return base64.b64encode(bytes([seed]) * 32).decode()


@pytest.fixture(autouse=True)
def clean_keyring(monkeypatch):
    """Each test gets its own keyring; none inherits another's cached state."""
    monkeypatch.delenv("FINANCEBUDDY_ENCRYPTION_KEYS", raising=False)
    monkeypatch.delenv("FINANCEBUDDY_ENCRYPTION_ACTIVE_KEY", raising=False)
    crypto.reset()
    yield
    crypto.reset()


@pytest.fixture
def single_key(monkeypatch):
    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", f"k1:{_key(1)}")
    crypto.reset()


# ── round trips ───────────────────────────────────────────────────────────────

def test_bytes_round_trip(single_key):
    blob = crypto.encrypt(b"holdings payload", aad="session-1")
    assert crypto.decrypt(blob, aad="session-1") == b"holdings payload"


def test_ciphertext_does_not_contain_the_plaintext(single_key):
    """A weak or accidentally-skipped encryption would show up here."""
    secret = b"ABCDE1234F salary 1800000"
    blob = crypto.encrypt(secret, aad="user-1")
    assert secret not in blob
    assert b"ABCDE1234F" not in blob


def test_text_round_trip(single_key):
    assert crypto.decrypt_text(crypto.encrypt_text("ABCDE1234F", aad="u1"), aad="u1") == "ABCDE1234F"


def test_json_round_trip(single_key):
    doc = {"fy": "2025-26", "salary": {"gross": 1_800_000}, "trades": [1, 2, 3]}
    blob = crypto.encrypt_json(doc, aad="session-9")
    assert crypto.decrypt_json(blob, aad="session-9") == doc


def test_none_passes_through(single_key):
    """A nullable column must stay nullable, and unset must differ from empty."""
    assert crypto.encrypt(None, aad="x") is None
    assert crypto.decrypt(None, aad="x") is None
    assert crypto.encrypt_text(None, aad="x") is None
    assert crypto.decrypt_text(None, aad="x") is None
    assert crypto.encrypt_json(None, aad="x") is None

    empty = crypto.encrypt(b"", aad="x")
    assert empty is not None
    assert crypto.decrypt(empty, aad="x") == b""


def test_memoryview_is_accepted(single_key):
    """psycopg returns bytea as a memoryview, not bytes."""
    blob = crypto.encrypt(b"payload", aad="s1")
    assert crypto.decrypt(memoryview(blob), aad="s1") == b"payload"


def test_encryption_is_randomised(single_key):
    """
    Same plaintext, same key, different ciphertext - a fresh nonce per write.

    A deterministic scheme would leak equality: an observer could tell which users
    share a PAN, or which sessions hold an identical portfolio, without decrypting.
    """
    a = crypto.encrypt(b"same", aad="s1")
    b = crypto.encrypt(b"same", aad="s1")
    assert a != b
    assert crypto.decrypt(a, aad="s1") == crypto.decrypt(b, aad="s1") == b"same"


# ── the associated-data binding ───────────────────────────────────────────────

def test_ciphertext_cannot_be_transplanted_to_another_row(single_key):
    """
    The attack this exists to stop.

    Someone with write access to the database - but no key - copies user A's
    encrypted holdings into user B's row. Encryption alone does not notice: the
    application would decrypt it happily and serve A's portfolio to B. Binding the
    ciphertext to its row id via GCM's associated data makes the copy fail.
    """
    stolen = crypto.encrypt(b"user A's portfolio", aad="session-A")

    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(stolen, aad="session-B")

    # ...and still works in its own row, so the test is not passing vacuously.
    assert crypto.decrypt(stolen, aad="session-A") == b"user A's portfolio"


def test_empty_aad_is_refused(single_key):
    """An empty aad would make every ciphertext transplantable."""
    with pytest.raises(ValueError):
        crypto.encrypt(b"x", aad="")
    with pytest.raises(ValueError):
        crypto.decrypt(crypto.encrypt(b"x", aad="s"), aad="")


# ── tampering ─────────────────────────────────────────────────────────────────

def test_modified_ciphertext_is_rejected(single_key):
    blob = bytearray(crypto.encrypt(b"holdings", aad="s1"))
    blob[-1] ^= 0x01  # flip one bit of the tag
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(bytes(blob), aad="s1")


def test_plaintext_in_an_encrypted_column_is_rejected(single_key):
    """
    A row that predates the migration, or a column someone wrote around the
    encryption layer. Reported rather than silently returned.
    """
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(b'{"salary": 1800000}', aad="s1")


@pytest.mark.parametrize("truncated", [b"FBE1", b"FBE1\x02k1", b"FBE1\x02k1" + b"\x00" * 5])
def test_truncated_values_are_rejected(single_key, truncated):
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(truncated, aad="s1")


def test_a_key_from_outside_the_keyring_cannot_read(monkeypatch):
    """An attacker who guesses the format still needs the key."""
    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", f"k1:{_key(1)}")
    crypto.reset()
    blob = crypto.encrypt(b"secret", aad="s1")

    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", f"k1:{_key(9)}")  # same id, wrong material
    crypto.reset()
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(blob, aad="s1")


# ── key rotation ──────────────────────────────────────────────────────────────

def test_old_keys_still_decrypt_after_rotation(monkeypatch):
    """
    Rotation must not orphan existing rows.

    The old key stays in the ring so anything written under it still reads; new
    writes use the active key, and rows re-encrypt as they are next written.
    """
    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", f"k1:{_key(1)}")
    crypto.reset()
    written_under_k1 = crypto.encrypt(b"old row", aad="s1")

    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", f"k1:{_key(1)},k2:{_key(2)}")
    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_ACTIVE_KEY", "k2")
    crypto.reset()

    assert crypto.decrypt(written_under_k1, aad="s1") == b"old row"

    written_under_k2 = crypto.encrypt(b"new row", aad="s1")
    assert crypto.decrypt(written_under_k2, aad="s1") == b"new row"
    assert written_under_k2[:8] != written_under_k1[:8], "new write did not use the active key"


def test_retiring_a_key_that_still_has_rows_is_reported(monkeypatch):
    """Dropping a key too early is data loss; it must be loud, not silent."""
    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", f"k1:{_key(1)}")
    crypto.reset()
    orphaned = crypto.encrypt(b"row", aad="s1")

    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", f"k2:{_key(2)}")
    crypto.reset()

    with pytest.raises(crypto.DecryptionFailed, match="not in the keyring"):
        crypto.decrypt(orphaned, aad="s1")


# ── configuration ─────────────────────────────────────────────────────────────

def test_missing_keyring_raises_rather_than_storing_plaintext():
    """
    Encryption that silently no-ops when unconfigured is worse than none: the
    deployment reports itself as encrypted and is not.
    """
    assert crypto.is_configured() is False
    with pytest.raises(crypto.EncryptionNotConfigured, match="FINANCEBUDDY_ENCRYPTION_KEYS"):
        crypto.encrypt(b"x", aad="s1")


def test_single_key_needs_no_active_key_setting(single_key):
    assert crypto.is_configured() is True
    assert crypto.decrypt(crypto.encrypt(b"x", aad="s"), aad="s") == b"x"


def test_multiple_keys_require_an_explicit_active_key(monkeypatch):
    """Guessing which of several keys is active risks writing under a retired one."""
    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", f"k1:{_key(1)},k2:{_key(2)}")
    crypto.reset()
    with pytest.raises(crypto.EncryptionNotConfigured, match="ACTIVE_KEY"):
        crypto.encrypt(b"x", aad="s1")


def test_active_key_must_exist_in_the_keyring(monkeypatch):
    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", f"k1:{_key(1)}")
    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_ACTIVE_KEY", "k7")
    crypto.reset()
    with pytest.raises(crypto.EncryptionNotConfigured, match="not in the keyring"):
        crypto.encrypt(b"x", aad="s1")


@pytest.mark.parametrize("bad,reason", [
    ("k1", "no colon"),
    ("k1:not-base64!!", "not base64"),
    (f":{_key(1)}", "empty id"),
    ("k1:" + base64.b64encode(b"tooshort").decode(), "wrong key length"),
])
def test_malformed_keyring_entries_are_rejected(monkeypatch, bad, reason):
    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", bad)
    crypto.reset()
    with pytest.raises(crypto.EncryptionNotConfigured):
        crypto.encrypt(b"x", aad="s1")


def test_a_short_key_is_rejected_rather_than_padded(monkeypatch):
    """AES-256 needs 32 bytes; anything shorter must fail loudly, not be stretched."""
    monkeypatch.setenv("FINANCEBUDDY_ENCRYPTION_KEYS", "k1:" + base64.b64encode(b"x" * 16).decode())
    crypto.reset()
    with pytest.raises(crypto.EncryptionNotConfigured, match="AES-256 needs 32"):
        crypto.encrypt(b"x", aad="s1")

def test_crypto_keyring_and_decrypt_json(monkeypatch):
    from shared import crypto

    with pytest.raises(crypto.EncryptionNotConfigured):
        crypto._parse_keyring("nocolon")

    with pytest.raises(crypto.EncryptionNotConfigured):
        crypto._parse_keyring(":badbase64!!!")

    assert crypto.decrypt_json(None, "aad") is None

    monkeypatch.setattr(crypto, "decrypt", lambda blob, aad: None)
    assert crypto.decrypt_json(b"anything", "aad") is None

