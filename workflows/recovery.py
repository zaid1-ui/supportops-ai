"""Error recovery (Part 3).

The ladder from ARCHITECTURE.md §8.3, in order:

    tool retry with backoff
      -> agent retry with the critique injected
        -> LLM fallback (primary model -> secondary)
          -> dead-letter to the human queue

Two rules hold throughout:

1. No silent failures. Every degradation emits a DEGRADED event. A system that
   quietly falls back looks healthy in metrics while serving worse answers, and
   nobody finds out until a customer complains.
2. Degrade to a human, never to a guess. When the ladder is exhausted the run
   escalates. It does not produce a best-effort answer.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from backend.app.core.logging import get_logger
from backend.app.models import EventType
from workflows.state import StateStore

logger = get_logger(__name__)

T = TypeVar("T")


class RecoveryExhausted(Exception):
    """Every rung of the ladder failed. The caller must route to a human."""


class ToolCallFailed(Exception):
    """An MCP tool call failed after its own retries."""


# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------

TOOL_MAX_ATTEMPTS = 3
TOOL_BASE_DELAY_S = 0.5

# Validation is capped separately and deliberately low. An LLM judging another
# LLM's revision can loop indefinitely, each loop costing a full agent run. Two
# retries, then a human looks at it.
VALIDATION_MAX_RETRIES = 2


def retry_tool(
    fn: Callable[[], T],
    *,
    store: StateStore,
    run_id: str,
    tool: str,
    agent: str | None = None,
    max_attempts: int = TOOL_MAX_ATTEMPTS,
) -> T:
    """Call a tool with exponential backoff. Emits before and after every attempt.

    Recording the call *before* execution is what makes a hung tool visible. If
    only successes were logged, a tool that never returns would leave no trace.
    """
    last: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        t0 = time.perf_counter()
        store.emit(
            run_id,
            EventType.TOOL_CALLED,
            agent=agent,
            tool=tool,
            payload={"attempt": attempt},
        )
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 — tools raise anything
            last = exc
            store.emit(
                run_id,
                EventType.TOOL_FAILED,
                agent=agent,
                tool=tool,
                payload={"attempt": attempt, "error": str(exc)},
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            if attempt < max_attempts:
                time.sleep(TOOL_BASE_DELAY_S * (2 ** (attempt - 1)))
        else:
            return result

    raise ToolCallFailed(f"{tool} failed after {max_attempts} attempts: {last}") from last


def note_degradation(store: StateStore, run_id: str, what: str, why: str) -> None:
    """Record that the system is running in a degraded mode.

    Called by the graceful-degradation paths: reranker down, vector store down,
    fallback model in use. Emitting this is mandatory — the point of the ladder
    is that operators can see when it fired.
    """
    store.emit(run_id, EventType.DEGRADED, payload={"component": what, "reason": why})
    logger.warning("degraded: %s (%s)", what, why)


def should_retry_validation(attempts: int) -> bool:
    """Whether a failed draft gets another revision pass."""
    return attempts < VALIDATION_MAX_RETRIES
