"""Model access for the AI layer.

Wraps the existing Gemini client in ``ai_service`` (model discovery, fallback
chain, working-model cache) rather than duplicating it.

The call is synchronous network I/O. From an async route or service, run it
off the event loop: ``await asyncio.to_thread(explain_portfolio, ...)``.
"""
from __future__ import annotations

from ai.guardrails import Generation


def gemini_generate(prompt: str) -> Generation | None:
    """Generate text with Gemini; None when no key is configured or every model fails."""
    import ai_service  # local import: keeps ``ai`` importable without the Gemini SDK settings

    text = ai_service._generate_with_gemini(prompt)
    if not text:
        return None
    model = ai_service._working_gemini_model or ai_service.DEFAULT_MODEL
    return Generation(text=text, model=model)
