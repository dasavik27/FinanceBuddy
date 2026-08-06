"""AIS schema validation and header normalization."""

import pytest

from domains.tax_expert import ais_parser
from domains.tax_expert.ais_schemas import (
    AISStructureChangedError,
    AISUnknownCodeError,
    clean_header,
    validate_schema,
)


def test_ais_clean_header_and_validation():
    cleaned = clean_header("  Total \n Amount (Rs.) ")
    assert "AMOUNT" in cleaned
    assert "\n" not in cleaned

    # Valid schema check for dividend_sft
    assert validate_schema("dividend_sft", ["SR. NO.", "REPORTED ON", "DIVIDEND AMOUNT", "STATUS"]) is True

    # Missing column in golden schema raises AISStructureChangedError
    with pytest.raises(AISStructureChangedError):
        validate_schema("dividend_sft", ["SR. NO.", "STATUS"])

def test_ais_validate_schema_structure_changed():
    from domains.tax_expert.ais_schemas import validate_schema, AISStructureChangedError

    with pytest.raises(AISStructureChangedError):
        validate_schema("salary_tds", ["SR. NO.", "WRONG COLUMN"])

def test_ais_schemas_nan_header_and_unknown_table():
    from domains.tax_expert.ais_schemas import clean_header, validate_schema

    assert clean_header(float("nan")) == ""
    assert validate_schema("unknown_table", ["A", "B"]) is True

