"""Gemini client and the legacy text entry points for market and stock AI output.

The model client (discovery, fallback chain, working-model cache) lives here.
What the model is asked and what is allowed back is decided in the guarded
layer, :mod:`ai.insights` (decision D5): facts in, description out, checked,
with a disclaimer and a template fallback. The adviser-style prompts that used
to be in this module are gone.
"""
import os
import logging
from datetime import datetime, timezone

from typing import Optional

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
FALLBACK_MODELS = [
    DEFAULT_MODEL,
    "gemini-3.6-flash",
    "gemini-3.1-pro-preview",
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-2.5-flash",
]

_working_gemini_model: Optional[str] = None
_discovered_models: Optional[list[str]] = None


def _get_candidate_models(genai) -> list[str]:
    """Get sorted candidate models, trying dynamic listing first."""
    global _working_gemini_model, _discovered_models

    if _working_gemini_model:
        return [_working_gemini_model]

    if _discovered_models is None:
        try:
            available = []
            for m in genai.list_models():
                methods = getattr(m, "supported_generation_methods", []) or []
                if "generateContent" in methods:
                    name = m.name.replace("models/", "")
                    available.append(name)
            if available:
                def model_rank(m_name: str) -> int:
                    m_lower = m_name.lower()
                    if "3.6-flash" in m_lower: return 0
                    if "3.1-pro" in m_lower: return 1
                    if "2.0-flash" in m_lower: return 2
                    if "flash" in m_lower: return 3
                    if "pro" in m_lower: return 4
                    return 5
                available.sort(key=model_rank)
                _discovered_models = available
                logger.info(f"Discovered {len(available)} available Gemini models. Preferred: {_discovered_models[:3]}")
        except Exception as e:
            logger.debug(f"Dynamic Gemini model discovery failed: {e}")
            _discovered_models = []

    if _discovered_models:
        return _discovered_models

    seen = set()
    return [m for m in FALLBACK_MODELS if m and not (m in seen or seen.add(m))]


def _generate_with_gemini(prompt: str) -> Optional[str]:
    """Attempt generation across supported Gemini models with fallback and working-model caching."""
    global _working_gemini_model
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Gemini configure error: {e}")
        return None

    models_to_try = _get_candidate_models(genai)
    last_err = None

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                if _working_gemini_model != model_name:
                    _working_gemini_model = model_name
                    logger.info(f"Gemini successfully generated content using model: {model_name}")
                return response.text
        except Exception as e:
            last_err = e
            # If the cached working model failed, invalidate cache and try others
            if _working_gemini_model == model_name:
                _working_gemini_model = None
            logger.debug(f"Gemini model {model_name} failed: {e}")
            continue

    logger.warning(f"All Gemini model attempts failed (last error: {last_err})")
    return None


def get_market_insight(market_data: list, opportunities: list = None) -> str:
    """Text of the guarded market summary (see ``ai.insights.market_insight``).

    Kept for the callers that store or return a plain string. Routes should use
    ``ai.insights.market_insight_response``, which also returns who generated
    the text, when, and the disclaimer. ``opportunities`` is ignored: the text
    describes figures and recommends nothing.
    """
    from ai.insights import market_insight  # local import: ai.provider imports this module

    return market_insight(market_data, now=datetime.now(timezone.utc)).text


def get_stock_analysis(symbol: str, stock_data: dict) -> str:
    """Text of the guarded description of one instrument (see ``ai.insights.stock_analysis``).

    Kept for the callers that return a plain string. Routes should use
    ``ai.insights.stock_analysis_response``.
    """
    from ai.insights import stock_analysis  # local import: ai.provider imports this module

    return stock_analysis(stock_data, now=datetime.now(timezone.utc)).text
