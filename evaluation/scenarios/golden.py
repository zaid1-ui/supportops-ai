"""Golden evaluation scenarios (Part 13).

Cases are data, not code, so a reviewer can read what is being tested and add to
it without touching the harness. Each case states its expected outcome up front —
that expectation is the author's judgement, recorded once, which is what lets the
harness score without an LLM judging another LLM.

The five categories match the assessment: agent, tool, retrieval, workflow,
response quality.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Retrieval — a small fixed corpus plus queries with known-correct sources.
# ---------------------------------------------------------------------------

RETRIEVAL_CORPUS = [
    {
        "filename": "exports.txt",
        "product_area": "exports",
        "content": (
            "# Timeout Behaviour\n\n"
            "An export exceeding 30 minutes is terminated and marked failed. Failed exports "
            "are not retried automatically; the user must start a new export.\n\n"
            "# Large Exports\n\n"
            "Exports above 50,000 rows are processed asynchronously and a download link is "
            "emailed on completion.\n"
        ),
    },
    {
        "filename": "billing.txt",
        "product_area": "billing",
        "content": (
            "# Refunds\n\n"
            "Refunds above $500 require manager approval and settle in 5 to 10 business days.\n\n"
            "# Duplicate Charges\n\n"
            "A duplicate charge is refunded in full once verified against the transaction log.\n"
        ),
    },
    {
        "filename": "auth.txt",
        "product_area": "authentication",
        "content": (
            "# Password Reset\n\n"
            "A password reset link expires after one hour. Requesting a new link invalidates "
            "the previous one.\n\n"
            "# Account Lockout\n\n"
            "Five failed sign-in attempts lock an account for fifteen minutes.\n"
        ),
    },
]

# query -> the filename that should rank first, and the product area to scope by.
# min_score is 0.0 because the absolute cosine value depends on the embedding
# model; what is under test is that the RIGHT source ranks first and that scoping
# excludes other areas. A real deployment raises min_score once its embedder's
# score distribution is characterised.
RETRIEVAL_CASES = [
    {"id": "ret-1", "query": "why did my large csv export fail",
     "product_area": "exports", "expect_source": "exports.txt", "min_score": 0.0},
    {"id": "ret-2", "query": "how long until my refund arrives",
     "product_area": "billing", "expect_source": "billing.txt", "min_score": 0.0},
    {"id": "ret-3", "query": "my password reset link stopped working",
     "product_area": "authentication", "expect_source": "auth.txt", "min_score": 0.0},
    # Scoping: an exports-scoped query must not return billing, even if the words overlap.
    {"id": "ret-4", "query": "approval required",
     "product_area": "exports", "expect_source": "exports.txt", "min_score": 0.0,
     "note": "scoping must exclude billing.txt despite the word 'approval'"},
]


# ---------------------------------------------------------------------------
# Agent — inputs with a known-correct classification / judgement.
# ---------------------------------------------------------------------------

# Triage cases. The rubric is deterministic enough to assert on.
TRIAGE_CASES = [
    {
        "id": "triage-outage",
        "ticket": {
            "subject": "Everything is down",
            "body": "Nobody on my team can log in. The whole service is unreachable.",
            "account_tier": "enterprise",
        },
        "expect_severity": "S1",
        "note": "explicit total outage -> S1",
    },
    {
        "id": "triage-howto",
        "ticket": {
            "subject": "How do I export to CSV?",
            "body": "I can't find the export button. Where is it?",
            "account_tier": "standard",
        },
        "expect_severity_in": ["S3", "S4"],
        "expect_intent": "how_to",
        "note": "a question with nothing broken -> low severity",
    },
    {
        "id": "triage-angry-trivial",
        "ticket": {
            "subject": "THIS IS UNACCEPTABLE",
            "body": "I am furious. The logo colour is wrong on my dashboard. Fix it NOW.",
            "account_tier": "standard",
        },
        "expect_severity_in": ["S3", "S4"],
        "note": "angry tone must not inflate a cosmetic issue to S1/S2",
    },
]


# ---------------------------------------------------------------------------
# Tool — MCP tools with known inputs and expected result shapes.
# ---------------------------------------------------------------------------

TOOL_CASES = [
    {"id": "tool-get-ticket", "tool": "get_ticket", "args": {"ticket_id": "SEED-1"},
     "expect_ok": True, "expect_keys": ["subject", "body"]},
    {"id": "tool-get-missing", "tool": "get_ticket", "args": {"ticket_id": "NOPE"},
     "expect_ok": False, "note": "missing id -> ok=False, not an exception"},
    {"id": "tool-update-safe", "tool": "update_ticket",
     "args": {"ticket_id": "SEED-1", "updates": {"severity": "S1"}},
     "expect_ok": True},
    {"id": "tool-update-unsafe", "tool": "update_ticket",
     "args": {"ticket_id": "SEED-1", "updates": {"customer_email": "evil@x.com"}},
     "expect_ok": False, "note": "non-whitelisted field must be rejected"},
    {"id": "tool-search", "tool": "search_knowledge",
     "args": {"query": "export timeout", "product_area": "exports"},
     "expect_ok": True, "note": "returns results dict"},
]


# ---------------------------------------------------------------------------
# Workflow — end-to-end structural expectations, checked from the event trace.
# ---------------------------------------------------------------------------

WORKFLOW_CASES = [
    {
        "id": "wf-resolution-gates",
        "workflow": "ticket_resolution",
        "ticket_id": "SEED-1",
        "expect_events": ["run_started", "task_started"],
        "expect_pauses_at": "response_approval",
        "note": "a resolution run must reach the mandatory approval gate, never auto-send",
    },
]


# ---------------------------------------------------------------------------
# Response quality — drafts with rules a good answer must satisfy.
# These are checked structurally: grounding = every claim has a citation,
# policy = no forbidden promise, completeness = addresses the question.
# ---------------------------------------------------------------------------

RESPONSE_QUALITY_CASES = [
    {
        "id": "rq-grounded",
        "draft": "Exports over 30 minutes are terminated and marked failed. Please start a new export.",
        "citations": [{"chunk_id": "c1", "source": "exports.txt", "page": 1, "score": 0.9}],
        "expect_grounded": True,
        "forbidden_phrases": ["we guarantee", "roadmap", "by next week"],
        "note": "claim is supported and makes no forbidden promise",
    },
    {
        "id": "rq-uncited",
        "draft": "This is a known bug and engineering will ship a fix by Friday.",
        "citations": [],
        "expect_grounded": False,
        "forbidden_phrases": ["by friday", "will ship"],
        "note": "roadmap commitment with no citation -> should fail grounding and policy",
    },
    {
        "id": "rq-policy",
        "draft": "I've gone ahead and issued your full $800 refund immediately.",
        "citations": [{"chunk_id": "c9", "source": "billing.txt", "page": 1, "score": 0.8}],
        "expect_grounded": True,
        "forbidden_phrases": ["issued your full $800 refund"],
        "note": "refund over $500 needs approval; an autonomous promise violates policy",
    },
]
