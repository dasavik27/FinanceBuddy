"""
test_encryption_at_rest_mocked.py

Mock-based equivalents of test_encryption_at_rest.py.
Verifies column encryption primitives, ciphertext guarantees, AAD binding,
and transplant attack prevention without needing a live Postgres database.
"""

import zlib
import pytest
from shared import crypto

PAN = "ZZZZZ9999Z"
SALARY = 4_242_424
FUND = "Very Distinctive Fund Name"
SESSION_ID_1 = "11111111-1111-1111-1111-111111111111"
SESSION_ID_2 = "22222222-2222-2222-2222-222222222222"


def test_pan_encryption_ciphertext_guarantees():
    """PAN ciphertext starts with MAGIC and does not leak plaintext."""
    encrypted = crypto.encrypt_text(PAN, aad="profiles:pan")
    assert encrypted.startswith(crypto.MAGIC)
    assert PAN.encode() not in encrypted
    assert PAN.lower().encode() not in encrypted

    # Decrypt restores original
    decrypted = crypto.decrypt_text(encrypted, aad="profiles:pan")
    assert decrypted == PAN


def test_portfolio_metrics_ciphertext_guarantees():
    """Portfolio metrics payload starts with MAGIC and conceals numerical values."""
    metrics = {"total_value": 987654.0, "total_invested": 500000.0}
    encrypted = crypto.encrypt_json(metrics, aad=SESSION_ID_1)

    assert encrypted.startswith(crypto.MAGIC)
    assert b"987654" not in encrypted

    decrypted = crypto.decrypt_json(encrypted, aad=SESSION_ID_1)
    assert decrypted["total_value"] == 987654.0


def test_holdings_ciphertext_cannot_be_decompressed_directly():
    """Holdings payload starts with MAGIC and is not readable via raw zlib decompress."""
    holdings_data = [{"Fund": FUND, "Units": 100.0, "NAV": 100.0}]
    # Compression + encryption
    compressed = zlib.compress(str(holdings_data).encode("utf-8"))
    encrypted = crypto.encrypt(compressed, aad=SESSION_ID_1)

    assert encrypted.startswith(crypto.MAGIC)
    assert FUND.encode() not in encrypted

    with pytest.raises(zlib.error):
        zlib.decompress(encrypted)

    # Decrypt + decompress restores content
    decrypted = crypto.decrypt(encrypted, aad=SESSION_ID_1)
    assert zlib.decompress(decrypted).decode("utf-8") == str(holdings_data)


def test_ais_document_ciphertext_guarantees():
    """AIS document conceals gross salary and PAN."""
    ais_data = {
        "fy": "2025-26",
        "personal": {"pan": PAN, "name": "At Rest"},
        "salary": {"gross": SALARY},
    }
    encrypted = crypto.encrypt_json(ais_data, aad=SESSION_ID_1)

    assert encrypted.startswith(crypto.MAGIC)
    assert str(SALARY).encode() not in encrypted
    assert PAN.encode() not in encrypted

    decrypted = crypto.decrypt_json(encrypted, aad=SESSION_ID_1)
    assert decrypted["salary"]["gross"] == SALARY


def test_payload_transplant_attack_fails():
    """
    Transplant attack: moving a ciphertext bound to session_id_1 to session_id_2
    must raise DecryptionFailed because AAD does not match.
    """
    payload = {"secret": "confidential_financial_records"}
    encrypted_for_session_1 = crypto.encrypt_json(payload, aad=SESSION_ID_1)

    # Attempting decryption under session 2's AAD must fail loudly
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt_json(encrypted_for_session_1, aad=SESSION_ID_2)
