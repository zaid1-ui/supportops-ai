"""LLM factory.

Implements the model tiering in ARCHITECTURE.md §8.2: classification runs on a
small fast model, reasoning on the stronger one. The tier is a property of the
job, declared per agent.

Provider routing
----------------
CrewAI executes model calls through litellm, and litellm identifies the provider
from a prefix on the model string — `xai/grok-3-mini`, `gemini/gemini-2.0-flash`,
`openai/gpt-4o-mini`. A bare name like `grok-3-mini` fails at call time with
"LLM Provider NOT provided", which is a confusing place to discover a config
error. So this factory validates the prefix up front and returns CrewAI's own
LLM type, which hands the string and base_url straight to litellm.
"""

from __future__ import annotations

from enum import Enum

from crewai import LLM

from backend.app.core.config import settings


class Tier(str, Enum):
    FAST = "fast"            # Classification / scoring. Cheap, low latency.
    REASONING = "reasoning"  # Analysis, drafting, critique.


# Reproducible classification (0.0) or the eval harness measures sampling noise.
_TEMPS: dict[Tier, float] = {Tier.FAST: 0.0, Tier.REASONING: 0.2}

# Providers whose model strings litellm recognises by prefix. Not exhaustive —
# just the ones this project has been used with — but enough to catch the common
# mistake of omitting the prefix entirely.
_KNOWN_PREFIXES = ("openai/", "xai/", "gemini/", "groq/", "anthropic/", "ollama/", "together/")


def _validated_model() -> str:
    model = settings.llm_model
    if "/" not in model:
        raise ValueError(
            f"LLM_MODEL={model!r} has no provider prefix. litellm needs one, e.g. "
            f"'xai/{model}', 'gemini/gemini-2.0-flash', or 'openai/gpt-4o-mini'. "
            f"Known prefixes: {', '.join(p.rstrip('/') for p in _KNOWN_PREFIXES)}."
        )
    return model


def get_llm(tier: Tier = Tier.REASONING) -> LLM:
    """Build a CrewAI LLM for the given tier.

    base_url is passed through, so any OpenAI-compatible endpoint works: xAI,
    Groq, a local vLLM. The provider prefix on LLM_MODEL is what selects the
    integration; base_url only overrides the endpoint within it.

    `max_retries` lets litellm back off and retry on a 429 rather than failing
    the whole crew. Free-tier providers meter by requests-per-minute, and a
    7-agent run fires far more calls than that per minute — without retries the
    first agent to hit the limit kills the run. Retries turn a rate limit into
    latency instead of a failure.
    """
    return LLM(
        model=_validated_model(),
        api_key=settings.resolved_llm_key,
        base_url=settings.llm_base_url or None,
        temperature=_TEMPS[tier],
        max_retries=settings.llm_max_retries,
    )