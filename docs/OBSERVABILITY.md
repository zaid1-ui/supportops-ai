# Observability & Evaluation

How the platform is measured, in production (Part 12) and in test (Part 13).

**Observability code:** `backend/app/api/metrics.py`, the `events` table, `/analytics`
**Evaluation code:** `evaluation/`, `scripts/evaluate.py`

The two share a foundation: the `events` table. Production metrics are aggregates over real runs' events; evaluation is a controlled set of runs whose events are checked against known-correct outcomes. One instrument, two uses.

---

## Part 12 — Observability

### The event trace is the single source of truth

Every metric the platform reports is derived from the `events` table (`backend/app/models/orchestration.py`). Nothing is instrumented separately. This is deliberate: a metric with its own instrumentation drifts from the behaviour it claims to describe, because the metric code and the behaviour code are edited at different times by different reasoning. Deriving everything from the events the orchestration layer already emits means the numbers cannot disagree with what actually happened.

Events are written by the state layer (`workflows/state.py`) as a run executes. Crucially, tool calls are recorded **before and after** execution, not only on success — a tool that hangs and never returns still leaves a `tool_called` event, so a stuck run is visible rather than silent.

### What is tracked

| Metric | Source events | Question it answers |
|---|---|---|
| Workflow completion rate | `run_completed` / finished runs | Do runs finish? |
| Failure rate | `run_failed` / finished runs | How often do they break? |
| Agent success rate | `task_completed` vs `task_failed`, per agent | Which agent is unreliable? |
| Tool usage | `tool_called`, per tool | Which tools carry the load? |
| Approval rate | `approval_decided` where approved/edited | Do humans accept the drafts? |
| Runs by status | `workflow_runs.status` | What is the queue doing now? |
| Degradations | `degraded` | When did a fallback fire? |

Exposed at `GET /metrics` (`MetricsResponse`) and rendered on the `/analytics` page.

### Design decisions

**The completion-rate denominator is finished runs, not all runs.** A run that is mid-flight or parked at a human gate is neither a success nor a failure yet. Counting those as incomplete would make the rate a function of how recently someone started work rather than of whether the platform works — the number would sag every time a batch of runs kicked off and recover as they drained, telling you about timing, not quality.

**Agent success is per-agent, from task events.** A run failing tells you something broke; it does not tell you *what*. Because every task emits `task_started` / `task_completed` / `task_failed` tagged with the agent, the failure is attributable: if the Diagnostic agent fails 40% of its tasks, that is visible without reading a single trace. This attribution is the payoff of the one-agent-one-job design (`AGENTS.md`).

**Tool calls counted before execution.** `tool_called` is emitted before the call, so a tool that fails or hangs still appears in usage counts. Counting only successes would make a broken tool look *unused* rather than *broken* — the worst possible signal.

**Degradations are events, not log lines.** When a fallback fires — a retry, a rate-limit backoff, a degraded retrieval path — it emits a `degraded` event. A platform that quietly degrades looks healthy in metrics while serving worse answers. Making degradation a first-class event means the `/analytics` view shows *when the system was not at full strength*, which is exactly what an operator needs and exactly what logs bury.

### Scaling note

At volume, `/metrics` would aggregate over a growing `events` table on every request. The path forward (stated in `ARCHITECTURE.md §8.2`) is a periodic rollup job writing pre-aggregated counts, with the dashboard reading the rollup rather than scanning raw events. Not built here — at this scale the live aggregate is fast — but the events table is the right foundation for it, because a rollup is a summary *of* the events, not a separate instrument.

---

## Part 13 — Evaluation Framework

### Principle: score from facts, never from an LLM judging an LLM

Every score is computed from a checkable fact — a classification equals the expected label, a tool returns `ok=False` on bad input, retrieval ranks the right source first. No LLM-as-judge anywhere. An LLM judge would put a second model into the measurement path, another thing that hallucinates, inside the code whose entire job is telling the truth about quality. Where a case genuinely needs judgement (is this the right answer), the *scenario author* records the expected outcome once, up front, and the harness compares against it. The judgement is human and fixed, not the model's and freshly-guessed each run.

This is why classification agents run at `temperature=0.0` (`agents/llm.py`): so a repeated eval measures the agent's quality, not the sampler's noise.

### The five evaluation types

The assessment names five. Each has its own evaluator in `evaluation/harness/harness.py`.

| Evaluation | What it checks | Needs LLM? |
|---|---|---|
| **Retrieval** | Right source ranked first; scoping excludes other product areas | No |
| **Tool** | Correct result shape; bad input rejected; unsafe writes blocked | No |
| **Response quality** | Grounding (claims cite sources); policy (no forbidden promise) | No |
| **Agent** | Triage classifies correctly against a known rubric | Yes — 1 call/case |
| **Workflow** | A run reaches the approval gate and never auto-sends | Yes — 1 run/case |

The first three are **deterministic and keyless** — they measure the parts of the platform that do not depend on the model, and run offline in milliseconds. The last two make **one agent call per case**, which fits inside a free-tier per-minute rate limit, and skip cleanly with an explanatory result when no key is configured, so the offline suite still reports a complete picture.

### Scenarios are data

Golden cases live in `evaluation/scenarios/golden.py` as plain data, not code, so a reviewer can read exactly what is tested and add cases without touching the harness. Each case states its expected outcome inline — that is the recorded human judgement the harness scores against.

Examples of what the cases pin down:

- **An outage is S1, an angry customer with a cosmetic bug is not.** The triage cases include a furious, all-caps ticket about a wrong logo colour — expected `S3`/`S4`. This is the exact failure the triage prompt guards against (tone-driven severity inflation), turned into a regression test.
- **`update_ticket` rejects `customer_email`.** A tool case sends a non-whitelisted field and expects `ok=False`. If a future edit widens the writable set by accident, this fails.
- **A resolution run pauses at `response_approval`.** The workflow case asserts, from the event trace, that the run reached the mandatory human gate — the structural guarantee that nothing reaches a customer autonomously.
- **An uncited roadmap promise fails grounding and policy.** A response-quality case with zero citations and "engineering will ship a fix by Friday" is expected to trip both detectors.

### Scoring

- **Partial credit per case.** A case is several checks; its score is the fraction that passed. An agent that gets severity right but routing wrong scores 0.5, not 0 — a single pass/fail would hide which half worked.
- **Two aggregates per category.** `pass_rate` (cases fully correct) and `mean_score` (average partial credit). They differ meaningfully: "every case half-right" and "half the cases perfect" have the same mean score but very different pass rates, and seeing both tells them apart.
- **`ERROR` is distinct from `FAIL`.** A case whose evaluator itself broke, or which was skipped for lack of a key, is `ERROR` — not counted as a genuine failure. Conflating "the platform is wrong" with "the test could not run" would make the suite lie in both directions.

### Running it

```bash
python -m scripts.evaluate            # all five; live suites run if an LLM key is set
python -m scripts.evaluate --offline  # the three deterministic suites only
```

The runner exits non-zero if any case genuinely failed (skips do not count), so it doubles as a CI gate rather than only a report.

### Verified

The three deterministic suites pass 12/12 offline with no API key. The two live suites dispatch one call per case and skip cleanly when no key is present. Run against a live model, the agent suite scores the triage rubric and the workflow suite confirms the approval gate from the event trace.

### What this does not do

- **No LLM-as-judge**, for the reason above.
- **No absolute-score threshold on retrieval.** The cosine value depends on the embedding model, so the retrieval cases test *ranking and scoping*, not a magic number. A real deployment sets a floor once its embedder's score distribution is known — the field is there, defaulted to 0.
- **No load or latency testing.** Correctness, not performance. Performance evaluation would need a different harness and a representative traffic model.
