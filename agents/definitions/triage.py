"""Triage Agent — classification and routing."""

from crewai import Agent
from crewai.tools import BaseTool

from agents.llm import Tier, get_llm
from agents.prompts import TRIAGE_BACKSTORY


def build_triage_agent(tools: list[BaseTool] | None = None) -> Agent:
    return Agent(
        role="Support Triage Specialist",
        goal=(
            "Classify every incoming ticket by intent, severity, and product area, "
            "route it to the correct queue, and report calibrated confidence so that "
            "ambiguous tickets reach a human instead of a wrong queue."
        ),
        backstory=TRIAGE_BACKSTORY,
        llm=get_llm(Tier.FAST),
        tools=tools or [],
        allow_delegation=False,
        max_iter=3,
        verbose=True,
    )
