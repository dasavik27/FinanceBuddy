"""
domains/budget/rules_safety.py - making user-authored categorization rules safe to run.

The hole this closes
--------------------
A user rule with match_type "regex" was stored verbatim and then executed server-side
against every transaction description:

    if re.search(r["pattern"], desc_str, re.IGNORECASE):

Measured on this codebase: the pattern `(a+)+$` against a 31-character description ran
for over two minutes without completing. The pattern is *persisted*, so it re-fires on
every upload and on every /rules/apply-all - a handful of requests wedges the API.

Why there is no runtime timeout
-------------------------------
CPython's `re` engine does not release the GIL while matching. A catastrophic pattern
therefore freezes the whole interpreter, not just its own thread, so the usual
mitigations - run it in a worker thread, cancel on a timer - cannot work. A subprocess
per match would work and costs more than the categorization itself.

That leaves one option: the check has to be conclusive *before* the pattern is ever
run, and it has to be a whitelist of shapes rather than a blacklist of known-bad ones.

The rule
--------
Catastrophic backtracking needs a quantifier applied to something that can match the
same input more than one way. In practice that means a quantified *group*: `(a+)+`,
`(a|a)*`, `(\\d+)*`. A quantifier on a single character or character class - `a+`,
`\\d{4}`, `[a-z]*` - cannot blow up on its own.

So: quantifiers on atoms are allowed, quantifiers on groups are not. Backreferences and
lookaround are rejected outright; both add backtracking that this analysis does not
model, and neither has a plausible use in "which category is this merchant".

This keeps the patterns people actually write - `swiggy|zomato`, `^UPI/`, `\\d{4}$`,
`amazon.*pay` - and rejects the ones that can hang the server.

Rules stored before this module existed are re-validated at match time, not trusted
because they are already in the table.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

MATCH_TYPES = ("contains", "exact", "starts_with", "ends_with", "regex")

# A rule pattern longer than this is not a merchant match, it is a payload.
MAX_PATTERN_LENGTH = 200

# Rules are applied per transaction, so the per-user count multiplies the cost of every
# upload. 200 is far more than anyone categorises by hand and still bounds the work.
MAX_RULES_PER_USER = 200

# Descriptions are truncated before matching. Bank narrations are ~100 chars; anything
# past this is padding, and the cap bounds the input side of the cost.
MAX_SUBJECT_LENGTH = 512

# A bounded repetition may not ask for more than this. `a{100000}` is linear but still
# builds a very large automaton.
MAX_REPETITION = 1_000

# More than this many quantifiers in one pattern is not a merchant rule.
MAX_QUANTIFIERS = 20

_CATEGORY_MAX_LENGTH = 64


class UnsafePattern(ValueError):
    """Raised when a rule pattern is rejected. The message is shown to the user."""


def _reject(message: str) -> "UnsafePattern":
    return UnsafePattern(message)


def _scan_regex(pattern: str) -> None:
    """
    Walk the pattern once, rejecting every construct the analysis cannot bound.

    A hand-written scan rather than parsing with `sre_parse`: that module is private,
    its AST changed shape between 3.8 and 3.11, and it *compiles* the pattern as a side
    effect - which for a pathological pattern is the thing we are trying to avoid doing.
    """
    quantifiers = 0

    # One flag per open group: "this group can match the same text more than one way",
    # which is true once it contains a quantifier or an alternation. Only an *ambiguous*
    # group is dangerous to repeat - `(a+)+` and `(a|a)*` explode, `(ab)+` cannot, because
    # there is exactly one way for `ab` to match. Tracking this instead of rejecting every
    # quantified group keeps ordinary patterns like `(?:INR)?\\d+` working.
    group_ambiguous: List[bool] = []

    i = 0
    n = len(pattern)

    # Set when the previous token was a closing paren, i.e. a quantifier here would apply
    # to a group; the second flag carries whether that group was ambiguous.
    prev_was_group = False
    prev_group_ambiguous = False

    def note_ambiguity() -> None:
        """Mark the innermost open group as ambiguous, if there is one."""
        if group_ambiguous:
            group_ambiguous[-1] = True

    def reject_repeat() -> None:
        raise _reject(
            "A repeat (* + ? {n}) may not be applied to a group that itself contains a "
            "repeat or an alternation - patterns like '(a+)+' or '(a|a)*' can hang the "
            "server. Repeat a character or character class instead, e.g. 'a+' or '[0-9]{4}'."
        )

    while i < n:
        ch = pattern[i]

        if ch == "\\":
            if i + 1 >= n:
                raise _reject("Pattern ends with a dangling backslash.")
            nxt = pattern[i + 1]
            if nxt.isdigit():
                raise _reject(
                    "Backreferences (\\1, \\2, ...) are not allowed in a rule pattern."
                )
            i += 2
            prev_was_group = False
            continue

        if ch == "[":
            # Character class: skip to the unescaped closing bracket.
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1  # a ']' first in a class is a literal
            while j < n and pattern[j] != "]":
                j += 2 if pattern[j] == "\\" else 1
            if j >= n:
                raise _reject("Unclosed character class '[' in pattern.")
            i = j + 1
            prev_was_group = False
            continue

        if ch == "(":
            if pattern.startswith("(?", i):
                if pattern.startswith("(?=", i) or pattern.startswith("(?!", i):
                    raise _reject("Lookahead ((?=...), (?!...)) is not allowed.")
                if pattern.startswith("(?<=", i) or pattern.startswith("(?<!", i):
                    raise _reject("Lookbehind ((?<=...), (?<!...)) is not allowed.")
                if pattern.startswith("(?(", i):
                    raise _reject("Conditional groups ((?(1)...)) are not allowed.")
                if pattern.startswith("(?P=", i):
                    raise _reject("Named backreferences ((?P=name)) are not allowed.")

                # The prefix has to be consumed here. Falling through with i += 1 would
                # leave the scanner on the '?', which it would then read as a quantifier
                # and use to mark the group ambiguous - so '(?:INR)?' was rejected as if
                # it were '(x?)?'.
                if pattern.startswith("(?:", i):
                    consumed = 3
                else:
                    named = re.match(r"\(\?P<\w+>", pattern[i:])
                    if not named:
                        raise _reject(
                            "Only plain '(...)' and non-capturing '(?:...)' groups are "
                            "allowed in a rule pattern."
                        )
                    consumed = named.end()
                group_ambiguous.append(False)
                i += consumed
                prev_was_group = False
                prev_group_ambiguous = False
                continue

            group_ambiguous.append(False)
            i += 1
            prev_was_group = False
            prev_group_ambiguous = False
            continue

        if ch == ")":
            if not group_ambiguous:
                raise _reject("Unbalanced ')' in pattern.")
            closed_ambiguous = group_ambiguous.pop()
            # Ambiguity propagates outward: a group containing an ambiguous group is
            # itself ambiguous, so `((a+))+` is caught at the outer repeat.
            if closed_ambiguous:
                note_ambiguity()
            i += 1
            prev_was_group = True
            prev_group_ambiguous = closed_ambiguous
            continue

        if ch == "|":
            note_ambiguity()
            i += 1
            prev_was_group = False
            continue

        if ch in "*+?":
            quantifiers += 1
            if prev_was_group and prev_group_ambiguous:
                reject_repeat()
            # A repeat anywhere makes the enclosing group ambiguous, which is what stops
            # `((ab)+)+` even though `(ab)+` on its own is fine.
            note_ambiguity()
            # A quantifier directly after another is a lazy marker ('+?', '*?'), not a
            # second level of repetition.
            i += 1
            if i < n and pattern[i] == "?":
                i += 1
            prev_was_group = False
            prev_group_ambiguous = False
            continue

        if ch == "{":
            close = pattern.find("}", i)
            body = pattern[i + 1: close] if close != -1 else ""
            if close == -1 or not re.fullmatch(r"\d*(,\d*)?", body) or body in ("", ","):
                # Not a repetition - a literal brace. Python treats it as a literal too.
                i += 1
                prev_was_group = False
                continue
            quantifiers += 1
            if prev_was_group and prev_group_ambiguous:
                reject_repeat()
            for bound in body.split(","):
                if bound and int(bound) > MAX_REPETITION:
                    raise _reject(f"Repetition counts above {MAX_REPETITION} are not allowed.")
            note_ambiguity()
            i = close + 1
            prev_was_group = False
            prev_group_ambiguous = False
            continue

        i += 1
        prev_was_group = False
        prev_group_ambiguous = False

    if group_ambiguous:
        raise _reject("Unclosed '(' in pattern.")
    if quantifiers > MAX_QUANTIFIERS:
        raise _reject(f"Pattern uses more than {MAX_QUANTIFIERS} repeats.")


def validate_pattern(pattern: str, match_type: str) -> str:
    """
    Validate a rule pattern, returning the normalised form to store.

    Raises UnsafePattern with a message intended for the user.
    """
    if match_type not in MATCH_TYPES:
        raise _reject(f"Unknown match type '{match_type}'. Use one of: {', '.join(MATCH_TYPES)}.")

    text = (pattern or "").strip()
    if not text:
        raise _reject("Pattern cannot be empty.")
    if len(text) > MAX_PATTERN_LENGTH:
        raise _reject(f"Pattern is longer than {MAX_PATTERN_LENGTH} characters.")
    if "\x00" in text:
        raise _reject("Pattern contains a null byte.")

    if match_type == "regex":
        _scan_regex(text)
        # Only now, once the shape is known to be bounded, is it safe to compile.
        try:
            re.compile(text, re.IGNORECASE)
        except re.error as e:
            raise _reject(f"Not a valid regular expression: {e}") from e

    return text


def validate_category(category: str) -> str:
    text = (category or "").strip()
    if not text:
        raise _reject("Category cannot be empty.")
    if len(text) > _CATEGORY_MAX_LENGTH:
        raise _reject(f"Category is longer than {_CATEGORY_MAX_LENGTH} characters.")
    return text


class CompiledRule:
    """
    One rule, prepared once and reused across every row of an upload.

    The old categorizer re-evaluated `r["type"]` and re-ran `re.search` with a raw
    pattern string for every transaction, so a 5,000-row statement recompiled each
    regex 5,000 times. Compilation happens here, once.
    """

    __slots__ = ("rule_id", "category", "match_type", "_needle", "_regex")

    def __init__(self, rule_id: str, pattern: str, category: str, match_type: str):
        self.rule_id = rule_id
        self.category = category
        self.match_type = match_type
        self._needle = pattern.strip().lower()
        self._regex = re.compile(pattern, re.IGNORECASE) if match_type == "regex" else None

    def matches(self, description: str, description_lower: str) -> bool:
        if self.match_type == "regex":
            return self._regex.search(description) is not None
        if self.match_type == "exact":
            return description_lower == self._needle
        if self.match_type == "starts_with":
            return description_lower.startswith(self._needle)
        if self.match_type == "ends_with":
            return description_lower.endswith(self._needle)
        return self._needle in description_lower


def compile_rules(rows: Iterable[Tuple[str, str, str, str]]) -> List[CompiledRule]:
    """
    Compile stored rules, dropping any that no longer pass validation.

    Rules written before this module existed were never checked, so being in the table
    is not evidence of being safe. A rule that fails here is skipped and logged rather
    than raising: one bad rule must not make the user's whole upload fail.
    """
    compiled: List[CompiledRule] = []
    for rule_id, pattern, category, match_type in rows:
        m_type = match_type if match_type in MATCH_TYPES else "contains"
        try:
            safe = validate_pattern(pattern, m_type)
        except UnsafePattern as e:
            logger.warning(
                "[budget.rules] skipping unsafe stored rule %s (%s): %s", rule_id, m_type, e
            )
            continue
        compiled.append(CompiledRule(rule_id, safe, category, m_type))
        if len(compiled) >= MAX_RULES_PER_USER:
            logger.warning(
                "[budget.rules] rule set truncated at %d; later rules were not applied",
                MAX_RULES_PER_USER,
            )
            break
    return compiled


def clip_subject(description: Optional[str]) -> str:
    """Bound the input side of matching. See MAX_SUBJECT_LENGTH."""
    if not description:
        return ""
    text = str(description)
    return text[:MAX_SUBJECT_LENGTH] if len(text) > MAX_SUBJECT_LENGTH else text
