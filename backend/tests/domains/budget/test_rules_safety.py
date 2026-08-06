
"""Budget rules safety validation."""

import pytest

from domains.budget import rules_safety


def test_rules_safety_char_class_and_invalid_regex():
    rules_safety.validate_pattern("[a]", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("[unclosed", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(a+)+", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("[", "regex")


def test_budget_rules_safety_unclosed_class():
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("[unclosed", "regex")


def test_clip_subject():
    assert rules_safety.clip_subject(None) == ""
    long_desc = "x" * 600
    assert len(rules_safety.clip_subject(long_desc)) == rules_safety.MAX_SUBJECT_LENGTH

def test_compile_rules_skips_unsafe_and_truncates(caplog):
    rows = [
        ("r1", "(a+)+", "Bad", "regex"),
        ("r2", "swiggy", "Food", "contains"),
        ("r3", "zomato", "Food", "contains"),
    ]
    compiled = rules_safety.compile_rules(rows)
    assert len(compiled) == 2
    many = [(f"r{i}", f"pat{i}", "Cat", "contains") for i in range(rules_safety.MAX_RULES_PER_USER + 5)]
    truncated = rules_safety.compile_rules(many)
    assert len(truncated) == rules_safety.MAX_RULES_PER_USER

def test_compiled_rule_all_match_types():
    regex_rule = rules_safety.CompiledRule("r1", r"^UPI", "Payments", "regex")
    assert regex_rule.matches("UPI/DR/123", "upi/dr/123")
    exact = rules_safety.CompiledRule("r2", "Swiggy", "Food", "exact")
    assert exact.matches("Swiggy", "swiggy")
    starts = rules_safety.CompiledRule("r3", "amazon", "Shopping", "starts_with")
    assert starts.matches("Amazon Pay", "amazon pay")
    ends = rules_safety.CompiledRule("r4", "mart", "Shopping", "ends_with")
    assert ends.matches("Big Mart", "big mart")
    contains = rules_safety.CompiledRule("r5", "zomato", "Food", "contains")
    assert contains.matches("Paid Zomato", "paid zomato")

def test_rules_safety_literal_brace_and_invalid_regex():
    rules_safety.validate_pattern("a{", "regex")  # literal open brace
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(?(", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("[", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(unclosed", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(", "regex")

def test_rules_safety_rejects_dangerous_patterns():
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(a+)+", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("foo\\", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(?=lookahead)", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("[unclosed", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("foo)", "regex")
    rules_safety.validate_pattern("swiggy", "contains")
    rules_safety.validate_category("Food & Dining")

def test_rules_safety_scanner_branches():
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern(r"\1abc", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("[^a-z", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("[a-z", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(?<=foo)", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(?<!foo)", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(?=(1))", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(?P=name)", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(?i:foo)", "regex")
    rules_safety.validate_pattern("(?:INR)?\\d+", "regex")
    rules_safety.validate_pattern("(?P<foo>bar)", "regex")
    rules_safety.validate_pattern("foo|bar", "regex")
    rules_safety.validate_pattern("a+?", "regex")
    rules_safety.validate_pattern("x{2,4}", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("a{1001}", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("(a+)+", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("((((((((((", "regex")
    too_many = "a+" * (rules_safety.MAX_QUANTIFIERS + 1)
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern(too_many, "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("x", "unknown")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("a\x00b", "contains")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("x" * 201, "contains")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("[", "regex")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_category("x" * 65)
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_category("")
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_category("   ")
    assert rules_safety.validate_category(" Food ") == "Food"

