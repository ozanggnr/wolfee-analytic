"""Turn verified facts into an explanation, with a deterministic fallback."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional, Sequence

from ai.guardrails import (
    DISCLAIMER,
    NO_OUTPUT,
    PROVIDER_ERROR,
    TEMPLATE_GENERATOR,
    AIResult,
    Fact,
    Generation,
    find_violations,
    one_line,
)
from ai.prompts import build_portfolio_prompt

logger = logging.getLogger(__name__)

Generator = Callable[[str], Optional[Generation]]

_TEMPLATE_HEADING = "Summary of the figures calculated for your portfolio:"


def explain_portfolio(
    facts: Sequence[Fact],
    *,
    now: datetime,
    inputs_as_of: datetime | None,
    generate: Generator | None = None,
) -> AIResult:
    """Explain ``facts`` in plain language.

    ``generate`` calls the model (see :mod:`ai.provider`); pass None to use the
    template only. ``now`` is supplied by the caller so the function stays
    deterministic. The model's text is used only if it passes the guardrails;
    whatever goes wrong with the model, the caller still gets a result.
    """
    facts = tuple(facts)
    if not facts:
        raise ValueError("at least one fact is required")

    generation, problems = _ask_model(generate, facts)
    if generation is not None and not problems:
        return AIResult(
            text=generation.text.strip(),
            generated_by=str(generation.model),
            generated_at=now,
            inputs_as_of=inputs_as_of,
            is_fallback=False,
            disclaimer=DISCLAIMER,
        )

    return AIResult(
        text=_template(facts),
        generated_by=TEMPLATE_GENERATOR,
        generated_at=now,
        inputs_as_of=inputs_as_of,
        is_fallback=True,
        disclaimer=DISCLAIMER,
        violations=problems,
    )


def _ask_model(
    generate: Generator | None, facts: Sequence[Fact]
) -> tuple[Generation | None, tuple[str, ...]]:
    """The model's answer and what is wrong with it; ``(None, ())`` when no model was asked."""
    if generate is None:
        return None, ()
    try:
        generation = generate(build_portfolio_prompt(facts))
        if generation is None:
            return None, (NO_OUTPUT,)
        problems = find_violations(generation.text, facts)
    except Exception as exc:  # a provider or guardrail failure must never break the page
        # The exception text is not logged: SDK errors can echo request details.
        logger.error("AI explanation failed (%s); using the template", type(exc).__name__)
        return None, (PROVIDER_ERROR,)

    if problems:
        logger.warning("AI explanation rejected by guardrails: %s", ", ".join(problems))
    return generation, problems


def _template(facts: Sequence[Fact]) -> str:
    lines = [f"{one_line(fact.label)}: {one_line(fact.value)}." for fact in facts]
    return "\n".join([_TEMPLATE_HEADING, *lines])
