"""LLM factory.

Implements the model tiering described in ARCHITECTURE.md §8.2: classification
work runs on a small fast model, reasoning work runs on the stronger one. The
tier is a property of the job, so it is declared per agent rather than globally.
"""

from __future__ import annotations

from enum import Enum

from langchain_openai import ChatOpenAI

from backend.app.core.config import settings


class Tier(str, Enum):
    """Which class of model a job needs."""

    FAST = "fast"        # Classification / scoring. Cheap, low latency.
    REASONING = "reasoning"  # Analysis, drafting, critique.


# Temperature is per-tier, not per-call. Classification must be reproducible
# (0.0) or the evaluation harness in Part 13 measures noise instead of quality.
_TIER_CONFIG: dict[Tier, dict] = {
    Tier.FAST: {"temperature": 0.0},
    Tier.REASONING: {"temperature": 0.2},
}


def get_llm(tier: Tier = Tier.REASONING) -> ChatOpenAI:
    """Build an LLM client for the given tier.

    Any OpenAI-compatible provider works via base_url — xAI/Grok, Together,
    a local vLLM. The agents do not know or care which; only this factory does.
    """
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.resolved_llm_key,
        base_url=settings.llm_base_url,
        **_TIER_CONFIG[tier],
    )
