"""Workflow orchestration (Part 3) and enterprise workflows (Part 8)."""

from workflows.hitl import ApprovalGate, ApprovalRequired
from workflows.recovery import RecoveryExhausted, ToolCallFailed, retry_tool
from workflows.state import StateStore, TaskTimer
from workflows.ticket_resolution import TicketResolutionWorkflow

# Consumed by POST /workflows/run (Part 10).
WORKFLOW_REGISTRY = {
    "ticket_resolution": TicketResolutionWorkflow,
}

__all__ = [
    "WORKFLOW_REGISTRY",
    "TicketResolutionWorkflow",
    "StateStore",
    "TaskTimer",
    "ApprovalGate",
    "ApprovalRequired",
    "RecoveryExhausted",
    "ToolCallFailed",
    "retry_tool",
]
