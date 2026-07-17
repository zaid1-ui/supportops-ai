"""Escalation Agent — risk scoring and tier routing."""

from crewai import Agent
from crewai.tools import BaseTool

from agents.llm import Tier, get_llm
from agents.prompts import ESCALATION_BACKSTORY


def build_escalation_agent(tools: list[BaseTool] | None = None) -> Agent:
    return Agent(
        role="Escalation Risk Analyst",
        goal=(
            "Score SLA, churn, and complexity risk on each ticket and escalate the "
            "ones heading somewhere bad before they get there."
        ),
        backstory=ESCALATION_BACKSTORY,
        llm=get_llm(Tier.FAST),
        tools=tools or [],
        allow_delegation=False,
        max_iter=3,
        verbose=True,
    )
