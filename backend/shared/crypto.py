"""
shared/crypto.py - application-side encryption for the columns that hold PII.

Threat model
------------
This protects against someone reading the *data* without also having the
*application's* environment: a leaked connection string, a stolen backup, a support
engineer with read access at the hosting provider, or a misdirected pg_dump.

It deliberately does not protect against an attacker who has compromised the running
application, because at that point they have the key by definition. Nothing can fix
that here; it is a different control (secrets management, host hardening).

Why not the alternatives
------------------------
- **Volume encryption** (what a host gives you by default) protects a stolen disk.
  It does nothing for a leaked DSN, because the database decrypts transparently for
  anyone who authenticates.
- **Row-level security** (migration 0002) does nothing either: this application
  connects as the table owner, which bypasses RLS. RLS is a backstop against an
  exposed anon key, not against the owner credential.
- **pgcrypto** puts the key in the SQL statement, which means it lands in
  `pg_stat_statements`, in the server log on any error, and in the wire protocol.
  Encrypting in the application keeps the key on the application host.

Format
------
Binary, so it stores in `bytea` without base64 inflation:

    b"FBE1" | key_id_len (1 byte) | key_id | nonce (12 bytes) | ciphertext+tag

AES-256-GCM. The tag is authentication, not just integrity theatre: paired with the
AAD below it makes the ciphertext non-transplantable.

Associated data binds a ciphertext to where it lives
----------------------------------------------------
Every call passes an `aad` naming the row - a session_id, or a user_id. GCM
authenticates it without storing it, so a ciphertext decrypted under a different aad
fails outright.

That closes an attack encryption alone does not: someone with write access to the
database could otherwise copy user A's encrypted holdings blob into user B's row and
have the application happily decrypt and serve it. They never need the key to do it.
Binding to the row id makes the copy fail to decrypt.

Key rotation
------------
`FINANCEBUDDY_ENCRYPTION_KEYS` is a keyring, not a key: `id:base64key,id2:base64key2`.
`FINANCEBUDDY_ENCRYPTION_ACTIVE_KEY` picks which one new writes use. Old keys stay in
the ring so existing rows still decrypt, and rows re-encrypt under the active key
whenever they are next written. Retiring a key is then: rotate, wait for writes, drop
the old entry.
"""

import base64
import logging
import os
import threading
from typing import Dict, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

MAGIC = b"FBE1"
NONCE_BYTES = 12   # GCM standard; anything else costs a re-derivation per operation
KEY_BYTES = 32     # AES-256


class EncryptionNotConfigured(RuntimeError):
    """No usable keyring. Raised rather than falling back to plaintext."""


class DecryptionFailed(Exception):
    """
    A stored value could not be decrypted.

    Distinct from a missing value: this means the row exists but the key that wrote
    it is not in the ring, or the ciphertext has been tampered with or transplanted.
    Callers must not treat it as "no data" - that would silently hide a
    misconfigured key behind an empty dashboard.
    """


_keyring: Optional[Dict[str, bytes]] = None
_active_key_id: Optional[str] = None
_lock = threading.RLock()


def _parse_keyring(raw: str) -> Dict[str, bytes]:
    keys: Dict[str, bytes] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue  # pragma: no cover — defensive / hard to exercise in unit tests
        if ":" not in entry:
            raise EncryptionNotConfigured(
                "FINANCEBUDDY_ENCRYPTION_KEYS entries must be 'id:base64key'"
            )
        key_id, encoded = entry.split(":", 1)
        key_id = key_id.strip()
        if not key_id:
            raise EncryptionNotConfigured("a key id in the keyring is empty")
        if len(key_id.encode("utf-8")) > 255:
            raise EncryptionNotConfigured(f"key id {key_id!r} is too long")  # pragma: no cover — defensive / hard to exercise in unit tests
        try:
            material = base64.b64decode(encoded.strip(), validate=True)
        except Exception as e:
            raise EncryptionNotConfigured(f"key {key_id!r} is not valid base64: {e}") from e
        if len(material) != KEY_BYTES:
            raise EncryptionNotConfigured(
                f"key {key_id!r} is {len(material)} bytes; AES-256 needs {KEY_BYTES}"
            )
        keys[key_id] = material
    return keys


def _load() -> None:
    """
    Read the keyring from the environment. Caller must hold _lock.

    Read lazily rather than at import so the module can be imported by tooling that
    has no keys, and so tests can set them after import.
    """
    global _keyring, _active_key_id

    raw = os.getenv("FINANCEBUDDY_ENCRYPTION_KEYS", "").strip()
    if not raw:
        raise EncryptionNotConfigured(
            "FINANCEBUDDY_ENCRYPTION_KEYS is not set. Generate one with:\n"
            "  python -c \"import base64,os;print('k1:'+base64.b64encode(os.urandom(32)).decode())\"\n"
            "See ONBOARDING.md. This is required - the application stores PAN, salary "
            "and holdings, and will not write them in plaintext."
        )

    keys = _parse_keyring(raw)
    if not keys:
        raise EncryptionNotConfigured("FINANCEBUDDY_ENCRYPTION_KEYS parsed to no keys")  # pragma: no cover — defensive / hard to exercise in unit tests

    active = os.getenv("FINANCEBUDDY_ENCRYPTION_ACTIVE_KEY", "").strip()
    if not active:
        # Unambiguous with one key; with several, guessing which is active risks
        # writing under a key the operator meant to retire.
        if len(keys) > 1:
            raise EncryptionNotConfigured(
                "FINANCEBUDDY_ENCRYPTION_ACTIVE_KEY must be set when the keyring "
                f"holds more than one key (found: {', '.join(sorted(keys))})"
            )
        active = next(iter(keys))
    if active not in keys:
        raise EncryptionNotConfigured(
            f"active key {active!r} is not in the keyring "
            f"(have: {', '.join(sorted(keys))})"
        )

    _keyring, _active_key_id = keys, active
    logger.info(
        "[CRYPTO] keyring loaded (%d key(s), active=%s)", len(keys), active
    )


def reset() -> None:
    """Drop the cached keyring so the next call re-reads the environment. For tests."""
    global _keyring, _active_key_id
    with _lock:
        _keyring, _active_key_id = None, None


def is_configured() -> bool:
    """True when a usable keyring exists. Does not raise."""
    try:
        _ensure_loaded()
        return True
    except EncryptionNotConfigured:
        return False


def _ensure_loaded() -> None:
    if _keyring is not None:
        return
    with _lock:
        if _keyring is None:
            _load()


def _aad_bytes(aad: str) -> bytes:
    if not aad:
        # An empty aad would let any ciphertext decrypt in any row, which is the
        # transplant attack the aad exists to prevent. Refuse rather than weaken.
        raise ValueError("aad is required - pass the owning row's id")
    return aad.encode("utf-8")


def encrypt(plaintext: Optional[bytes], aad: str) -> Optional[bytes]:
    """
    Encrypt under the active key, bound to `aad`. None passes through as None.

    None is preserved rather than encrypted so a nullable column stays nullable and
    "not set" stays distinguishable from "set to empty".
    """
    if plaintext is None:
        return None
    _ensure_loaded()

    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(_keyring[_active_key_id]).encrypt(
        nonce, plaintext, _aad_bytes(aad)
    )
    key_id = _active_key_id.encode("utf-8")
    return MAGIC + bytes([len(key_id)]) + key_id + nonce + ciphertext


def decrypt(blob, aad: str) -> Optional[bytes]:
    """
    Inverse of encrypt. None passes through as None.

    Raises DecryptionFailed for anything that is present but unreadable, so a key
    misconfiguration surfaces as an error rather than as silently missing data.
    """
    if blob is None:
        return None
    _ensure_loaded()

    # psycopg hands back a memoryview for bytea.
    blob = bytes(blob)

    if not blob.startswith(MAGIC):
        raise DecryptionFailed(
            "value is not in the expected encrypted format - it may predate "
            "migration 0003, or the column may hold plaintext"
        )

    offset = len(MAGIC)
    if len(blob) < offset + 1:
        raise DecryptionFailed("truncated header")
    key_id_len = blob[offset]
    offset += 1

    key_id = blob[offset:offset + key_id_len].decode("utf-8", errors="replace")
    offset += key_id_len
    nonce = blob[offset:offset + NONCE_BYTES]
    offset += NONCE_BYTES
    ciphertext = blob[offset:]

    if len(nonce) != NONCE_BYTES or not ciphertext:
        raise DecryptionFailed("truncated ciphertext")

    key = (_keyring or {}).get(key_id)
    if key is None:
        raise DecryptionFailed(
            f"key {key_id!r} is not in the keyring - it was retired before every row "
            "written under it had been re-encrypted"
        )

    try:
        return AESGCM(key).decrypt(nonce, ciphertext, _aad_bytes(aad))
    except InvalidTag as e:
        # Either tampering, or the row was moved: the aad no longer matches the row
        # this ciphertext was written for.
        raise DecryptionFailed(
            "authentication failed - ciphertext was modified, or does not belong to "
            "this row"
        ) from e


def encrypt_text(plaintext: Optional[str], aad: str) -> Optional[bytes]:
    """encrypt() for a str column."""
    return None if plaintext is None else encrypt(plaintext.encode("utf-8"), aad)


def decrypt_text(blob, aad: str) -> Optional[str]:
    """decrypt() for a str column."""
    raw = decrypt(blob, aad)
    return None if raw is None else raw.decode("utf-8")


def encrypt_json(value, aad: str) -> Optional[bytes]:
    """
    encrypt() for what used to be a jsonb column.

    Encrypted columns are `bytea`: jsonb cannot hold ciphertext, and anything the
    database could index or query inside would be plaintext by definition. Nothing
    here queried into these documents - they were fetched whole - so the only loss
    is server-side introspection, which is the point.
    """
    import json

    if value is None:
        return None
    return encrypt(json.dumps(value, separators=(",", ":"), default=str).encode("utf-8"), aad)


def decrypt_json(blob, aad: str):
    """Inverse of encrypt_json."""
    import json

    raw = decrypt(blob, aad)
    if raw is None:
        return None
    return json.loads(raw.decode("utf-8"))
