"""Agent definitions. Documented in docs/AGENTS.md."""

from agents.definitions.diagnostic import build_diagnostic_agent
from agents.definitions.escalation import build_escalation_agent
from agents.definitions.reporting import build_reporting_agent
from agents.definitions.research import build_research_agent
from agents.definitions.resolution import build_resolution_agent
from agents.definitions.triage import build_triage_agent
from agents.definitions.validation import build_validation_agent

# Name -> builder. Consumed by the workflow layer (Part 3) and by GET /agents.
AGENT_REGISTRY = {
    "triage": build_triage_agent,
    "research": build_research_agent,
    "diagnostic": build_diagnostic_agent,
    "resolution": build_resolution_agent,
    "validation": build_validation_agent,
    "escalation": build_escalation_agent,
    "reporting": build_reporting_agent,
}

__all__ = [
    "AGENT_REGISTRY",
    "build_triage_agent",
    "build_research_agent",
    "build_diagnostic_agent",
    "build_resolution_agent",
    "build_validation_agent",
    "build_escalation_agent",
    "build_reporting_agent",
]
