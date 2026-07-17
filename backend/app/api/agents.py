"""Agent routes (Part 10)."""

from __future__ import annotations

import time

from crewai import Crew, Process, Task
from fastapi import APIRouter, HTTPException, status

from agents.definitions import AGENT_REGISTRY
from backend.app.api.deps import CurrentUser, DbSession
from backend.app.core.logging import get_logger
from backend.app.schemas.api import AgentExecuteRequest, AgentExecuteResponse, AgentInfo
from mcp_tools.registry import build_tools

router = APIRouter(prefix="/agents", tags=["agents"])
logger = get_logger(__name__)

# Mirrors agents/llm.py tier assignment. Surfaced so the frontend's Agent
# Monitoring module can show which agents are cheap and which are not.
_TIERS = {
    "triage": "fast",
    "research": "reasoning",
    "diagnostic": "reasoning",
    "resolution": "reasoning",
    "validation": "reasoning",
    "escalation": "fast",
    "reporting": "reasoning",
}


@router.get("", response_model=list[AgentInfo])
def list_agents(db: DbSession, user: CurrentUser) -> list[AgentInfo]:
    tools = build_tools(db)
    out = []
    for name, builder in AGENT_REGISTRY.items():
        agent = builder(tools.get(name, []))
        out.append(
            AgentInfo(
                name=name,
                role=agent.role,
                goal=agent.goal,
                tier=_TIERS.get(name, "reasoning"),
                tools=[t.name for t in (agent.tools or [])],
                max_iter=agent.max_iter,
                allow_delegation=agent.allow_delegation,
            )
        )
    return out


@router.post("/execute", response_model=AgentExecuteResponse)
def execute_agent(
    payload: AgentExecuteRequest, db: DbSession, user: CurrentUser
) -> AgentExecuteResponse:
    """Run a single agent against an ad-hoc task.

    A debugging and evaluation surface, not the production path — production
    work goes through a workflow, which carries state, gates and a trace. This
    endpoint deliberately has none of those, so it cannot send anything to a
    customer: the agents that could are only reachable through a crew that
    stops at an approval gate.
    """
    if payload.agent not in AGENT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent '{payload.agent}'. Available: {', '.join(AGENT_REGISTRY)}",
        )

    agent = AGENT_REGISTRY[payload.agent](build_tools(db).get(payload.agent, []))
    task = Task(
        description=payload.task,
        expected_output="A direct response to the task.",
        agent=agent,
    )

    t0 = time.perf_counter()
    try:
        result = Crew(agents=[agent], tasks=[task], process=Process.sequential).kickoff()
    except Exception as exc:
        logger.exception("agent execution failed: %s", payload.agent)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Agent execution failed: {exc}"
        ) from exc

    return AgentExecuteResponse(
        agent=payload.agent,
        output=str(result),
        duration_ms=(time.perf_counter() - t0) * 1000,
    )
