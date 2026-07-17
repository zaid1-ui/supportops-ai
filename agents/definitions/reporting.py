"""Reporting Agent — report generation."""

from crewai import Agent
from crewai.tools import BaseTool

from agents.llm import Tier, get_llm
from agents.prompts import REPORTING_BACKSTORY


def build_reporting_agent(tools: list[BaseTool] | None = None) -> Agent:
    return Agent(
        role="Support Operations Analyst",
        goal=(
            "Turn workflow and queue data into reports that lead with the finding and "
            "end in specific, owned recommendations."
        ),
        backstory=REPORTING_BACKSTORY,
        llm=get_llm(Tier.REASONING),
        tools=tools or [],
        allow_delegation=False,
        max_iter=5,
        verbose=True,
    )
