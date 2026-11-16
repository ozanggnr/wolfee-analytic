"""Turn verified facts into an explanation, with a deterministic fallback."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional, Sequence

from ai.guardrails import (
    MARKET_DISCLAIMER,
    NO_OUTPUT,
    PORTFOLIO_DISCLAIMER,
    PROVIDER_ERROR,
    TEMPLATE_GENERATOR,
    AIResult,
    Fact,
    Generation,
    find_violations,
    one_line,
)
from ai.prompts import build_market_prompt, build_portfolio_prompt, build_stock_prompt

logger = logging.getLogger(__name__)

Generator = Callable[[str], Optional[Generation]]
PromptBuilder = Callable[[Sequence[Fact]], str]

_PORTFOLIO_HEADING = "Summary of the figures calculated for your portfolio:"
_MARKET_HEADING = "Wolfee AI market summary. Figures calculated from today's market data:"
_STOCK_HEADING = "Wolfee AI summary. Figures calculated for this instrument:"


def explain_portfolio(
    facts: Sequence[Fact],
    *,
    now: datetime,
    inputs_as_of: datetime | None,
    generate: Generator | None = None,
) -> AIResult:
    """Explain portfolio ``facts`` in plain language.

    ``generate`` calls the model (see :mod:`ai.provider`); pass None to use the
    template only. ``now`` is supplied by the caller so the function stays
    deterministic. The model's text is used only if it passes the guardrails;
    whatever goes wrong with the model, the caller still gets a result.
    """
    return _explain(facts, now, inputs_as_of, generate, build_portfolio_prompt, _PORTFOLIO_HEADING,
                    PORTFOLIO_DISCLAIMER)


def explain_market(
    facts: Sequence[Fact],
    *,
    now: datetime,
    inputs_as_of: datetime | None,
    generate: Generator | None = None,
) -> AIResult:
    """Describe today's market ``facts``; same guarantees as :func:`explain_portfolio`."""
    return _explain(facts, now, inputs_as_of, generate, build_market_prompt, _MARKET_HEADING,
                    MARKET_DISCLAIMER)


def explain_stock(
    facts: Sequence[Fact],
    *,
    now: datetime,
    inputs_as_of: datetime | None,
    generate: Generator | None = None,
) -> AIResult:
    """Describe one instrument's ``facts``; same guarantees as :func:`explain_portfolio`."""
    return _explain(facts, now, inputs_as_of, generate, build_stock_prompt, _STOCK_HEADING,
                    MARKET_DISCLAIMER)


def response_fields(result: AIResult) -> dict:
    """The provenance fields every AI response carries (API_CONTRACT §5.4.1), JSON-ready.

    ``violations`` is deliberately left out: it is for logs, never for the client.
    """
    return {
        "generated_by": result.generated_by,
        "generated_at": result.generated_at.isoformat(),
        "inputs_as_of": None if result.inputs_as_of is None else result.inputs_as_of.isoformat(),
        "is_fallback": result.is_fallback,
        "disclaimer": result.disclaimer,
    }


def _explain(
    facts: Sequence[Fact],
    now: datetime,
    inputs_as_of: datetime | None,
    generate: Generator | None,
    build_prompt: PromptBuilder,
    heading: str,
    disclaimer: str,
) -> AIResult:
    facts = tuple(facts)
    if not facts:
        raise ValueError("at least one fact is required")

    generation, problems = _ask_model(generate, facts, build_prompt)
    if generation is not None and not problems:
        return AIResult(
            text=generation.text.strip(),
            generated_by=str(generation.model),
            generated_at=now,
            inputs_as_of=inputs_as_of,
            is_fallback=False,
            disclaimer=disclaimer,
        )

    return AIResult(
        text=_template(facts, heading),
        generated_by=TEMPLATE_GENERATOR,
        generated_at=now,
        inputs_as_of=inputs_as_of,
        is_fallback=True,
        disclaimer=disclaimer,
        violations=problems,
    )


def _ask_model(
    generate: Generator | None, facts: Sequence[Fact], build_prompt: PromptBuilder
) -> tuple[Generation | None, tuple[str, ...]]:
    """The model's answer and what is wrong with it; ``(None, ())`` when no model was asked."""
    if generate is None:
        return None, ()
    try:
        generation = generate(build_prompt(facts))
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


def _template(facts: Sequence[Fact], heading: str) -> str:
    lines = [f"{one_line(fact.label)}: {one_line(fact.value)}." for fact in facts]
    return "\n".join([heading, *lines])
