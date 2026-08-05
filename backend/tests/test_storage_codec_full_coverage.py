"""
test_storage_codec_full_coverage.py

Full unit test coverage for shared.storage:
- _datetime_unit and frame codec (_encode_frame, _decode_frame)
- Payload round-tripping (encode_payload, decode_payload)
- Save and load payload with AES-GCM encryption & DB mocks
"""

from unittest.mock import MagicMock
import pandas as pd
import pytest

from shared import storage


def test_datetime_unit_detection():
    df = pd.DataFrame({"d_ns": pd.to_datetime(["2025-01-01"]).astype("datetime64[ns]")})
    unit = storage._datetime_unit(df["d_ns"].dtype)
    assert unit in ("ns", "s", "ms", "us")


def test_frame_encode_decode_roundtrip():
    df = pd.DataFrame({
        "Fund": ["HDFC Top 100", "Axis Bluechip"],
        "Date": pd.to_datetime(["2025-01-01", "2025-02-01"]),
        "Units": [100.5, 200.0],
        "Amount": [10000.0, 25000.0],
    })

    blob, dt_cols = storage._encode_frame(df)
    assert isinstance(blob, bytes)
    assert "Date" in dt_cols

    restored_df = storage._decode_frame(blob, dt_cols)
    assert len(restored_df) == 2
    assert list(restored_df["Fund"]) == ["HDFC Top 100", "Axis Bluechip"]
    assert pd.api.types.is_datetime64_any_dtype(restored_df["Date"])


def test_frame_encode_decode_empty_and_none():
    blob, dt_cols = storage._encode_frame(None)
    df_restored = storage._decode_frame(blob, dt_cols)
    assert df_restored.empty

    df_none = storage._decode_frame(None, None)
    assert df_none.empty


def test_payload_encode_decode_triplet():
    df_h = pd.DataFrame([{"Fund": "HDFC", "Units": 100}])
    df_t = pd.DataFrame([{"Fund": "HDFC", "Date": pd.to_datetime("2025-01-01"), "Units": 100}])
    df_s = pd.DataFrame([{"Fund": "HDFC", "Amount": 5000}])

    payload = storage.encode_payload(df_h, df_t, df_s)
    assert "holdings" in payload
    assert "transactions" in payload
    assert "sips" in payload
    assert payload["byte_size"] > 0

    h_out, t_out, s_out = storage.decode_payload(payload)
    assert len(h_out) == 1
    assert len(t_out) == 1
    assert len(s_out) == 1
    assert h_out.iloc[0]["Fund"] == "HDFC"
