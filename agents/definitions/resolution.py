"""Resolution Agent — action decision and customer draft."""

from crewai import Agent
from crewai.tools import BaseTool

from agents.llm import Tier, get_llm
from agents.prompts import RESOLUTION_BACKSTORY


def build_resolution_agent(tools: list[BaseTool] | None = None) -> Agent:
    return Agent(
        role="Support Resolution Specialist",
        goal=(
            "Decide the correct action and draft a plain, fully cited customer reply "
            "that a human reviewer can approve without rewriting."
        ),
        backstory=RESOLUTION_BACKSTORY,
        llm=get_llm(Tier.REASONING),
        tools=tools or [],
        allow_delegation=False,
        max_iter=5,
        verbose=True,
    )
