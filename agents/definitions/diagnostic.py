"""Diagnostic Agent — root cause hypothesis."""

from crewai import Agent
from crewai.tools import BaseTool

from agents.llm import Tier, get_llm
from agents.prompts import DIAGNOSTIC_BACKSTORY


def build_diagnostic_agent(tools: list[BaseTool] | None = None) -> Agent:
    return Agent(
        role="Support Diagnostic Engineer",
        goal=(
            "Reason from reported symptoms and cited evidence to the most probable "
            "root cause, with confidence that tracks the evidence rather than the "
            "fluency of the explanation."
        ),
        backstory=DIAGNOSTIC_BACKSTORY,
        llm=get_llm(Tier.REASONING),
        tools=tools or [],
        allow_delegation=False,
        max_iter=5,
        verbose=True,
    )
