"""MCP resources — read-only reference data.

Resources differ from tools: they're not actions, they're static or
slow-changing reference material an agent can look up on its own, without
a targeted question. Backing them by the same DB/config nothing else in
the app doesn't own keeps them from drifting out of sync with reality.
"""

from __future__ import annotations

import json

TICKET_SCHEMA = {
    "id": "string, primary key",
    "subject": "string",
    "body": "string, the customer's original message",
    "status": "enum: open | pending_customer | resolved",
    "account_tier": "string, e.g. free | pro | enterprise",
    "intent": "string, agent-classified, writable via update_ticket",
    "severity": "string, agent-classified, writable via update_ticket",
    "product_area": "string, agent-classified, writable via update_ticket",
    "queue": "string, agent-classified, writable via update_ticket",
    "reopen_count": "integer",
    "message_count": "integer",
    "sla_hours": "integer, hours allowed before SLA breach",
    "created_at": "ISO 8601 timestamp",
}

SLA_POLICY = {
    "breach_threshold_pct": 100,
    "at_risk_threshold_pct": 75,
    "note": (
        "queue_pressure buckets tickets by age/sla_hours. at_risk starts at "
        "75% of the SLA window elapsed — this is the same threshold the "
        "Escalation Agent's prompt is calibrated against. If this number "
        "changes, the prompt must change with it."
    ),
}


def register_schema_resources(mcp):
    @mcp.resource("schema://ticket")
    def ticket_schema() -> str:
        """Field reference for the Ticket object returned by ticket tools."""
        return json.dumps(TICKET_SCHEMA, indent=2)

    @mcp.resource("policy://sla")
    def sla_policy() -> str:
        """SLA breach and at-risk thresholds used by queue_pressure."""
        return json.dumps(SLA_POLICY, indent=2)