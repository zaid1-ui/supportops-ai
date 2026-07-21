"""Evaluation primitives (Part 13).

Scores are computed from checkable facts, not from an LLM's opinion of an LLM.
An LLM-as-judge would add a second model into the measurement path — another
thing that hallucinates, inside the code whose whole job is telling the truth
about quality. Where a check needs judgement (is this answer relevant), the
scenario states the expected answer up front and the harness compares against
it, so the judgement is the author's, made once, not the model's, made freshly
each run.

Everything here is deterministic given a fixed model temperature. Classification
agents run at temperature 0.0 precisely so these scores measure quality rather
than sampling noise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"  # The eval itself broke — distinct from a genuine FAIL.


@dataclass
class CheckResult:
    """One assertion within a case."""

    name: str
    passed: bool
    detail: str = ""

    @property
    def mark(self) -> str:
        return "PASS" if self.passed else "FAIL"


@dataclass
class CaseResult:
    """The outcome of one evaluation case: several checks, one verdict."""

    case_id: str
    category: str
    checks: list[CheckResult] = field(default_factory=list)
    outcome: Outcome = Outcome.PASS
    error: str | None = None
    duration_ms: float = 0.0

    def finalise(self) -> CaseResult:
        if self.error is not None:
            self.outcome = Outcome.ERROR
        elif all(c.passed for c in self.checks):
            self.outcome = Outcome.PASS
        else:
            self.outcome = Outcome.FAIL
        return self

    @property
    def score(self) -> float:
        """Fraction of checks that passed. Partial credit is informative — an
        agent that gets severity right but routing wrong is not a total loss,
        and a single pass/fail would hide that."""
        if not self.checks:
            return 0.0
        return sum(c.passed for c in self.checks) / len(self.checks)


@dataclass
class SuiteResult:
    """Aggregate over a category of cases."""

    category: str
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(c.outcome is Outcome.PASS for c in self.cases)

    @property
    def errored(self) -> int:
        return sum(c.outcome is Outcome.ERROR for c in self.cases)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def mean_score(self) -> float:
        """Average partial-credit score. Distinguishes 'every case half-right'
        from 'half the cases fully right', which pass_rate alone cannot."""
        return sum(c.score for c in self.cases) / self.total if self.total else 0.0


# --------------------------------------------------------------------------
# Reusable checks
# --------------------------------------------------------------------------


def check_equal(name: str, actual, expected) -> CheckResult:
    ok = actual == expected
    return CheckResult(name, ok, "" if ok else f"expected {expected!r}, got {actual!r}")


def check_in(name: str, actual, allowed: set) -> CheckResult:
    ok = actual in allowed
    return CheckResult(name, ok, "" if ok else f"{actual!r} not in {allowed}")


def check_ge(name: str, actual: float, threshold: float) -> CheckResult:
    ok = actual >= threshold
    return CheckResult(name, ok, "" if ok else f"{actual:.3f} < {threshold}")


def check_true(name: str, actual: bool) -> CheckResult:
    return CheckResult(name, bool(actual), "" if actual else "expected true")


def check_contains(name: str, haystack: str, needle: str) -> CheckResult:
    ok = needle.lower() in (haystack or "").lower()
    return CheckResult(name, ok, "" if ok else f"{needle!r} not found")
