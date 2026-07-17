"""Research Agent — grounded evidence retrieval."""

from crewai import Agent
from crewai.tools import BaseTool

from agents.llm import Tier, get_llm
from agents.prompts import RESEARCH_BACKSTORY


def build_research_agent(tools: list[BaseTool] | None = None) -> Agent:
    return Agent(
        role="Knowledge Research Analyst",
        goal=(
            "Retrieve cited evidence that answers the ticket, or declare an explicit "
            "knowledge gap. Never pass an uncited claim downstream."
        ),
        backstory=RESEARCH_BACKSTORY,
        llm=get_llm(Tier.REASONING),
        tools=tools or [],
        allow_delegation=False,
        # Higher than the others: multi-query reformulation is the documented
        # remedy for the false-gap failure mode (docs/AGENTS.md).
        max_iter=8,
        verbose=True,
    )
