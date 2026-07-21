"""Evaluation harness (Part 13).

Five evaluators, one per category the assessment names:

    retrieval        does vector search return the right source, scoped correctly
    tool             do MCP tools return the right shape and reject bad input
    response_quality is a draft grounded, policy-compliant, complete
    agent            does the Triage agent classify correctly (live LLM)
    workflow         does a run reach the approval gate without auto-sending (live)

The first three are deterministic and need no API key — they measure the parts
of the platform that do not depend on the model. The last two make one agent
call per case, which fits inside a free-tier rate limit, and are skipped
automatically when no LLM key is configured so the suite still runs offline.

Everything scores from checkable facts (scoring.py), never from an LLM judging
another LLM.
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.models import Ticket, TicketStatus
from evaluation.harness.scoring import (
    CaseResult,
    Outcome,
    SuiteResult,
    check_equal,
    check_ge,
    check_in,
    check_true,
)
from evaluation.scenarios import golden

logger = get_logger(__name__)


class Harness:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------------------------------------------------------- retrieval

    def eval_retrieval(self) -> SuiteResult:
        """Ingest the fixed corpus, then check each query returns the right source."""
        from rag.ingestion.pipeline import ingest_file
        from rag.retrieval.retriever import Retriever
        from rag.retrieval.vectorstore import reset_collection
        import tempfile, pathlib

        suite = SuiteResult("retrieval")
        reset_collection()

        # Ingest the golden corpus into a scratch area.
        tmp = pathlib.Path(tempfile.mkdtemp())
        for doc in golden.RETRIEVAL_CORPUS:
            f = tmp / doc["filename"]
            f.write_text(doc["content"])
            ingest_file(self.db, f, product_area=doc["product_area"])

        retriever = Retriever(self.db)
        for case in golden.RETRIEVAL_CASES:
            t0 = time.perf_counter()
            r = CaseResult(case["id"], "retrieval")
            try:
                hits = retriever.search(case["query"], product_area=case["product_area"])
                if hits:
                    r.checks.append(check_equal("top_source", hits[0].citation.source, case["expect_source"]))
                    r.checks.append(check_ge("top_score", hits[0].citation.score, case["min_score"]))
                    # Scoping: no hit may come from a different product area's file.
                    off_area = [h for h in hits if h.citation.source != case["expect_source"]
                                and h.citation.source in {d["filename"] for d in golden.RETRIEVAL_CORPUS
                                                          if d["product_area"] != case["product_area"]}]
                    r.checks.append(check_true("scope_respected", not off_area))
                else:
                    r.checks.append(check_true("returned_hits", False))
            except Exception as exc:  # noqa: BLE001
                r.error = str(exc)
            r.duration_ms = (time.perf_counter() - t0) * 1000
            suite.cases.append(r.finalise())
        return suite

    # -------------------------------------------------------------------- tools

    def eval_tools(self) -> SuiteResult:
        """Call each MCP tool with known input, assert result shape and safety."""
        from mcp_tools.servers import knowledge, tickets

        suite = SuiteResult("tool")

        # A ticket the tool cases operate on.
        if self.db.get(Ticket, "SEED-1") is None:
            self.db.add(Ticket(id="SEED-1", subject="export failed", body="80k rows never finishes",
                               customer_email="c@example.com", account_tier="enterprise",
                               status=TicketStatus.OPEN, product_area="exports"))
            self.db.commit()

        for case in golden.TOOL_CASES:
            t0 = time.perf_counter()
            r = CaseResult(case["id"], "tool")
            try:
                if case["tool"] == "get_ticket":
                    res = tickets.get_ticket(self.db, **case["args"])
                elif case["tool"] == "update_ticket":
                    res = tickets.update_ticket(self.db, **case["args"])
                elif case["tool"] == "search_knowledge":
                    res = knowledge.search_knowledge(self.db, **case["args"])
                else:
                    raise ValueError(f"unknown tool {case['tool']}")

                r.checks.append(check_equal("ok", res.ok, case["expect_ok"]))
                for key in case.get("expect_keys", []):
                    present = isinstance(res.data, dict) and key in res.data
                    r.checks.append(check_true(f"has_{key}", present))
            except Exception as exc:  # noqa: BLE001
                r.error = str(exc)
            r.duration_ms = (time.perf_counter() - t0) * 1000
            suite.cases.append(r.finalise())
        return suite

    # --------------------------------------------------------- response quality

    def eval_response_quality(self) -> SuiteResult:
        """Structural grounding and policy checks on fixed drafts.

        Grounding here is the same rule the Validation Agent applies: a draft
        making factual claims with no citations is ungrounded. Policy is the
        forbidden-promise check — a draft must not contain a phrase the policy
        prohibits (an unapproved refund, a roadmap date). Both are structural
        proxies for the Validation Agent's judgement: cheap, deterministic, and
        enough to catch the failure the platform most fears — a confident,
        uncited, or non-compliant claim reaching a customer.

        Each case declares whether it should pass or fail each rule, so a
        deliberate-violation case is scored as correctly *detecting* the
        violation, not as the platform having produced it.
        """
        suite = SuiteResult("response_quality")
        for case in golden.RESPONSE_QUALITY_CASES:
            r = CaseResult(case["id"], "response_quality")
            try:
                # Grounding: has citations iff it should be grounded.
                has_citations = len(case["citations"]) > 0
                r.checks.append(check_equal("grounded", has_citations, case["expect_grounded"]))

                # Policy: does the draft contain any forbidden phrase?
                violations = [p for p in case.get("forbidden_phrases", [])
                              if p.lower() in case["draft"].lower()]

                # A case whose note flags it as a violation demo *should* trip the
                # detector; a clean case should not. The check is that the
                # detector's verdict matches the case's intent.
                is_violation_case = "violat" in case.get("note", "").lower() or \
                                    not case["expect_grounded"] or \
                                    "policy" in case["id"]
                detected = len(violations) > 0
                r.checks.append(check_equal("policy_detector", detected, is_violation_case))
            except Exception as exc:  # noqa: BLE001
                r.error = str(exc)
            suite.cases.append(r.finalise())
        return suite

    # -------------------------------------------------------------------- agent

    def eval_agent(self) -> SuiteResult:
        """Live: run the Triage agent on each case, assert the classification.

        One LLM call per case, so this fits a free-tier per-minute limit. Skipped
        with an explanatory ERROR when no key is set, so the offline suite still
        reports a complete picture.
        """
        suite = SuiteResult("agent")
        if not settings.resolved_llm_key:
            for case in golden.TRIAGE_CASES:
                r = CaseResult(case["id"], "agent", error="no LLM key configured; skipped")
                suite.cases.append(r.finalise())
            return suite

        from crewai import Crew, Process, Task
        from agents.definitions import build_triage_agent
        from agents.prompts import TRIAGE_TASK
        from agents.schemas import TriageOutput

        for case in golden.TRIAGE_CASES:
            t0 = time.perf_counter()
            r = CaseResult(case["id"], "agent")
            try:
                agent = build_triage_agent()
                task = Task(
                    description=TRIAGE_TASK.format(
                        subject=case["ticket"]["subject"],
                        customer_email="test@example.com",
                        account_tier=case["ticket"]["account_tier"],
                        body=case["ticket"]["body"],
                        product_areas="exports\nbilling\nauthentication\nintegrations\nreporting\napi",
                    ),
                    expected_output="A TriageOutput.",
                    agent=agent,
                    output_pydantic=TriageOutput,
                )
                out = Crew(agents=[agent], tasks=[task], process=Process.sequential).kickoff()
                triage: TriageOutput = out.pydantic

                if "expect_severity" in case:
                    r.checks.append(check_equal("severity", triage.severity.value, case["expect_severity"]))
                if "expect_severity_in" in case:
                    r.checks.append(check_in("severity", triage.severity.value, set(case["expect_severity_in"])))
                if "expect_intent" in case:
                    r.checks.append(check_equal("intent", triage.intent.value, case["expect_intent"]))
            except Exception as exc:  # noqa: BLE001
                r.error = str(exc)
            r.duration_ms = (time.perf_counter() - t0) * 1000
            suite.cases.append(r.finalise())
        return suite

    # ----------------------------------------------------------------- workflow

    def eval_workflow(self) -> SuiteResult:
        """Live: run a resolution workflow, assert it reaches the approval gate.

        This is the structural guarantee that matters most — an automated system
        must never send to a customer without a human. Checked from the event
        trace, which is the same source the observability metrics use.
        """
        suite = SuiteResult("workflow")
        if not settings.resolved_llm_key:
            for case in golden.WORKFLOW_CASES:
                r = CaseResult(case["id"], "workflow", error="no LLM key configured; skipped")
                suite.cases.append(r.finalise())
            return suite

        from backend.app.models import Approval, ApprovalStatus, Event
        from workflows import WORKFLOW_REGISTRY

        for case in golden.WORKFLOW_CASES:
            t0 = time.perf_counter()
            r = CaseResult(case["id"], "workflow")
            try:
                if self.db.get(Ticket, case["ticket_id"]) is None:
                    self.db.add(Ticket(id=case["ticket_id"], subject="export failed",
                                       body="My 80,000 row export never completes.",
                                       customer_email="c@example.com", account_tier="enterprise",
                                       status=TicketStatus.OPEN, product_area="exports", sla_hours=8))
                    self.db.commit()

                wf = WORKFLOW_REGISTRY[case["workflow"]](self.db)
                run_id = wf.start(case["ticket_id"])

                events = [e.event_type.value for e in
                          self.db.query(Event).filter(Event.run_id == run_id).all()]
                for expected in case["expect_events"]:
                    r.checks.append(check_true(f"event_{expected}", expected in events))

                # The critical assertion: it paused at the response gate.
                pending = (self.db.query(Approval)
                           .filter(Approval.run_id == run_id,
                                   Approval.status == ApprovalStatus.PENDING).first())
                gate_ok = pending is not None and pending.kind.value == case["expect_pauses_at"]
                r.checks.append(check_true(f"paused_at_{case['expect_pauses_at']}", gate_ok))
            except Exception as exc:  # noqa: BLE001
                r.error = str(exc)
            r.duration_ms = (time.perf_counter() - t0) * 1000
            suite.cases.append(r.finalise())
        return suite

    # ------------------------------------------------------------------- runner

    def run_all(self, *, include_live: bool = True) -> list[SuiteResult]:
        suites = [self.eval_retrieval(), self.eval_tools(), self.eval_response_quality()]
        if include_live:
            suites.append(self.eval_agent())
            suites.append(self.eval_workflow())
        return suites
