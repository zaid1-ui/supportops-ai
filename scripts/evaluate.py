"""Evaluation runner (Part 13).

Usage:
    python -m scripts.evaluate              # all suites (live agent/workflow if key set)
    python -m scripts.evaluate --offline    # deterministic suites only, no LLM

Prints a per-category report and an overall summary, then exits non-zero if any
case failed — so this doubles as a CI gate, not just a report.
"""

from __future__ import annotations

import argparse
import sys

from backend.app.core.database import SessionLocal, init_db
from evaluation.harness import Harness
from evaluation.harness.scoring import Outcome, SuiteResult


def _print_suite(suite: SuiteResult) -> None:
    print(f"\n{suite.category.upper()}  "
          f"({suite.passed}/{suite.total} passed, mean score {suite.mean_score:.0%})")
    for case in suite.cases:
        symbol = {Outcome.PASS: "  PASS", Outcome.FAIL: "  FAIL", Outcome.ERROR: "  ERR "}[case.outcome]
        extra = ""
        if case.outcome is Outcome.ERROR:
            extra = f"  ({case.error})"
        elif case.outcome is Outcome.FAIL:
            fails = [f"{c.name}: {c.detail}" for c in case.checks if not c.passed]
            extra = "  " + "; ".join(fails)
        dur = f"{case.duration_ms:.0f}ms" if case.duration_ms else ""
        print(f"  {symbol}  {case.case_id:22s} {dur:>7s}{extra}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SupportOps AI evaluation harness.")
    parser.add_argument("--offline", action="store_true",
                        help="Run only deterministic suites (no LLM calls).")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        harness = Harness(db)
        suites = harness.run_all(include_live=not args.offline)

        for suite in suites:
            _print_suite(suite)

        total = sum(s.total for s in suites)
        passed = sum(s.passed for s in suites)
        errored = sum(s.errored for s in suites)
        failed = total - passed - errored

        print("\n" + "=" * 52)
        print(f"OVERALL  {passed}/{total} passed"
              + (f", {failed} failed" if failed else "")
              + (f", {errored} skipped/errored" if errored else ""))
        print("=" * 52)

        # Non-zero exit on a genuine failure (not on a skipped live suite).
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
