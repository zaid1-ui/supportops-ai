"""Workflow orchestration (Part 3) and enterprise workflows (Part 8)."""

from workflows.context import AssembledContext, ContextBlock, ContextEngine
from workflows.escalation_risk import EscalationRiskWorkflow
from workflows.hitl import ApprovalGate, ApprovalRequired
from workflows.knowledge_gap import KnowledgeGapWorkflow
from workflows.recovery import RecoveryExhausted, ToolCallFailed, retry_tool
from workflows.state import StateStore, TaskTimer
from workflows.ticket_resolution import TicketResolutionWorkflow

# Consumed by POST /workflows/run (Part 10). Every workflow takes (db) and
# exposes start(ticket_id) / resume(run_id), so the route dispatches uniformly.
WORKFLOW_REGISTRY = {
    "ticket_resolution": TicketResolutionWorkflow,
    "knowledge_gap_review": KnowledgeGapWorkflow,
    "escalation_risk_assessment": EscalationRiskWorkflow,
}

# The batch workflows scan a queue rather than acting on one ticket. The API
# uses this to skip the ticket_id requirement.
BATCH_WORKFLOWS = {"knowledge_gap_review", "escalation_risk_assessment"}

__all__ = [
    "WORKFLOW_REGISTRY", "BATCH_WORKFLOWS",
    "TicketResolutionWorkflow", "KnowledgeGapWorkflow", "EscalationRiskWorkflow",
    "ContextEngine", "ContextBlock", "AssembledContext",
    "StateStore", "TaskTimer", "ApprovalGate", "ApprovalRequired",
    "RecoveryExhausted", "ToolCallFailed", "retry_tool",
]
