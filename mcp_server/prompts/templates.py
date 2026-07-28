"""MCP prompts — reusable prompt templates.

Centralising these on the server means a wording fix happens once, not once
per agent file that happened to inline the same instruction.
"""

from __future__ import annotations


def register_prompt_templates(mcp):
    @mcp.prompt()
    def classify_ticket(subject: str, body: str) -> str:
        """Prompt template for classifying a ticket's intent, severity, and product area."""
        return (
            "Classify this support ticket.\n\n"
            f"Subject: {subject}\n"
            f"Body: {body}\n\n"
            "Return:\n"
            "- intent: the customer's underlying goal, one short phrase\n"
            "- severity: low | medium | high | critical\n"
            "- product_area: the product area this concerns\n\n"
            "Base severity on customer impact, not on tone. A calmly worded "
            "outage report is still critical."
        )

    @mcp.prompt()
    def escalation_summary(ticket_id: str, at_risk_data: str) -> str:
        """Prompt template for summarizing why a ticket is being escalated."""
        return (
            f"Ticket {ticket_id} is approaching or has breached its SLA.\n\n"
            f"Queue pressure data: {at_risk_data}\n\n"
            "Write a 2-3 sentence escalation summary for a human reviewer: "
            "what the ticket is about, why it's time-sensitive, and what "
            "action is being requested. Do not resolve or close the ticket "
            "yourself — escalation is a request for human attention, not "
            "an action you complete on your own."
        )