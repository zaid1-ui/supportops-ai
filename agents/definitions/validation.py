"""Validation Agent — the quality gate."""

from crewai import Agent
from crewai.tools import BaseTool

from agents.llm import Tier, get_llm
from agents.prompts import VALIDATION_BACKSTORY


def build_validation_agent(tools: list[BaseTool] | None = None) -> Agent:
    return Agent(
        role="Response Quality Reviewer",
        goal=(
            "Fail any draft containing an ungrounded claim, a policy violation, or an "
            "unanswered question, and return a critique specific enough to act on."
        ),
        backstory=VALIDATION_BACKSTORY,
        llm=get_llm(Tier.REASONING),
        tools=tools or [],
        # A reviewer that can delegate would ask the author to mark its own work.
        allow_delegation=False,
        max_iter=4,
        verbose=True,
    )
