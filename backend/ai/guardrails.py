"""Types and output checks shared by the AI layer.

``find_violations`` is a tripwire, not a proof of correctness. It rejects text
that states a figure which was not supplied, spells a figure out in words,
reads as advice, a prediction or a guarantee, or contains markup. It cannot
tell whether a supplied figure is attached to the right label, so the prompt
remains the first control and the disclaimer the last. Rejected text is never
shown to the user.

Callers must render the returned text as plain text (never as HTML or markdown).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Sequence

DISCLAIMER = (
    "This is an automated explanation of figures calculated by Wolfee Analytics from your "
    "recorded transactions and from market data that may be delayed. It is general information, "
    "not investment advice or a recommendation to buy or sell, and not a guarantee of future results."
)

TEMPLATE_GENERATOR = "template"
MAX_TEXT_LENGTH = 2000

EMPTY = "empty"
NO_OUTPUT = "no_output"
TOO_LONG = "too_long"
UNGROUNDED_NUMBER = "ungrounded_number"
NUMBER_WORD = "number_word"
PROHIBITED_LANGUAGE = "prohibited_language"
MARKUP = "markup"
PROVIDER_ERROR = "provider_error"

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_MINUS_SIGNS = "-−–"
_MARKUP = re.compile(r"[<>`]|\]\(")

_UNITS = (
    "zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    "sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    "hundred|thousand|million|billion|trillion"
)
# "one" on its own is ordinary prose ("one holding"); it only counts next to a unit.
_NUMBER_WORDS = re.compile(
    rf"\b(?:{_UNITS})\b"
    r"|\bone (?:percent|per cent|pct|third|quarter|half|hundred|thousand|million|billion)\b"
    r"|\b(?:half|halved|double|doubled|doubling|triple|tripled|twice|tenfold)\b",
    re.IGNORECASE,
)

_ACTIONS = "buy|buying|sell|selling|invest|investing|add|adding|trim|trimming|reduce|reducing"
_PROHIBITED = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bguarantee",
        r"\brecommend",
        r"\bsuggest",
        r"\badvis(?:e|ing)\b",
        r"\b(?:should|must|ought to|need to|may want to|might want to)\b",
        rf"\b(?:consider|worth|time to|opportunity to)\b.{{0,20}}\b(?:{_ACTIONS})\b",
        r"(?:^|[.!?;:] )(?:buy|sell|hold|invest)\b",
        r"\b(?:buy|sell|invest) (?:now|more|today)\b",
        r"\b(?:entry|exit) point\b",
        r"\b(?:price target|target price)\b",
        r"\b(?:will|going to|likely to|expected to|set to|bound to|poised to)\b",
        r"\b(?:undervalued|overvalued|bargain)\b",
        r"\brisk[- ]free\b",
        r"\bcan(?:no|')?t lose\b",
        r"\b(?:your|trusted) financial advis[eo]r\b",
    )
)


@dataclass(frozen=True)
class Fact:
    """One verified figure, already formatted by deterministic code.

    Numbers appearing in ``label`` or ``value`` become figures the model may
    quote, so never build a Fact from free text a user typed (a portfolio name,
    a note). Identifiers must be validated first (``quant.symbols``).
    """

    label: str
    value: str


@dataclass(frozen=True)
class Generation:
    """Raw text from a model and the name of the model that produced it."""

    text: str
    model: str


@dataclass(frozen=True)
class AIResult:
    """An explanation plus the traceability fields every AI response must carry.

    ``violations`` records why the template was used instead of the model's
    text; it is for logs and audits, not for display.
    """

    text: str
    generated_by: str
    generated_at: datetime
    inputs_as_of: datetime | None
    is_fallback: bool
    disclaimer: str
    violations: tuple[str, ...] = ()


def one_line(text: object) -> str:
    """Collapse whitespace and drop angle brackets so a value stays on its own line as plain text."""
    return " ".join(str(text).replace("<", " ").replace(">", " ").split())


def find_violations(text: object, facts: Sequence[Fact]) -> tuple[str, ...]:
    """Reasons ``text`` must not be shown, given the only ``facts`` it may use."""
    if not isinstance(text, str) or not text.strip():
        return (EMPTY,)
    if len(text) > MAX_TEXT_LENGTH:
        return (TOO_LONG,)

    plain = _plain(text)
    violations: list[str] = []
    if _has_ungrounded_number(plain, facts):
        violations.append(UNGROUNDED_NUMBER)
    if _NUMBER_WORDS.search(plain):
        violations.append(NUMBER_WORD)
    if any(pattern.search(plain) for pattern in _PROHIBITED):
        violations.append(PROHIBITED_LANGUAGE)
    if _MARKUP.search(plain):
        violations.append(MARKUP)
    return tuple(violations)


def _plain(text: str) -> str:
    """Fold look-alike characters, remove invisible ones and collapse whitespace before matching."""
    folded = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    return " ".join(folded.split())


def _numbers(text: str) -> list[tuple[str, str]]:
    """Every number in ``text`` as (canonical magnitude, sign), sign being "-", "+" or ""."""
    found = []
    for match in _NUMBER.finditer(text):
        start = match.start()
        before = text[start - 1] if start > 0 else ""
        # In "2026-01-04" or "3-5" the dash is a separator, not a sign.
        is_separator = start > 1 and text[start - 2].isalnum()
        if before in _MINUS_SIGNS and before and not is_separator:
            sign = "-"
        else:
            sign = "+" if before == "+" else ""
        found.append((_canonical(match.group()), sign))
    return found


def _has_ungrounded_number(text: str, facts: Sequence[Fact]) -> bool:
    """True if ``text`` states a number absent from the facts, or one with the opposite sign."""
    supplied = _numbers(" | ".join(_plain(f"{fact.label} {fact.value}") for fact in facts))
    magnitudes = {value for value, _ in supplied}
    negatives = {value for value, sign in supplied if sign == "-"}
    non_negatives = {value for value, sign in supplied if sign != "-"}

    for value, sign in _numbers(text):
        if value not in magnitudes:
            return True
        if sign == "-" and value not in negatives:
            return True
        if sign == "+" and value not in non_negatives:
            return True
    return False


def _canonical(token: str) -> str:
    """Canonical form of a number so ``20,450.00`` and ``20450`` compare equal."""
    try:
        return format(Decimal(token.replace(",", "")).normalize(), "f")
    except InvalidOperation:
        return token
