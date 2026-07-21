# Context Engineering

**Code:** `workflows/context.py`

Part 5 requires five context types and a documented strategy for sources, prioritisation, compression, and retrieval.

---

## The Problem

An agent's context window is a budget, not a container. Every token spent on a stale conversation turn is a token not spent on the retrieved document that actually answers the ticket.

The failure mode that matters is silent. Without a budget, context assembly is "concatenate everything and hope": the prompt overflows, the provider truncates from wherever it likes, and **the piece that gets cut is invisible**. The agent then answers confidently from a context it doesn't know was mutilated, and nothing in the trace says so.

Cutting deliberately, worst-first, and recording the cut — that is the whole job.

---

## 1. Context Sources

| Source | Contains | Origin | Cost |
|---|---|---|---|
| **Task** | Current workflow state — classification, evidence count, hypothesis, retry count | `WorkflowState` in memory | Free, tiny |
| **User** | Reviewer identity, role, approval authority | `users` table | Free, tiny |
| **Enterprise** | Retrieved KB chunks with citations, plus standing policy | ChromaDB + constant | One embedding call, large |
| **Long-term** | Resolved tickets with the same product area and intent | `tickets` table | One query, medium |
| **Short-term** | Recent conversation turns | Ticket thread | Free, unbounded |

### Why each earns its place

**Task context** is what stops an agent from re-deriving what a previous agent established. The Diagnostic Agent given the Triage classification doesn't re-classify. It also carries `validation_attempts`, so a retry knows it's a retry.

**User context** is here for a reason that isn't obvious: it changes what an agent should *write*, not just what the UI shows. A draft going to a Tier-1 agent shouldn't assume the engineering context a Tier-2 reviewer has. The role is already known — spending ~20 tokens to tell the agent who's reading is cheap.

**Enterprise context** is the grounding guarantee made concrete. Everything an agent is permitted to assert about the product comes from here. It is also the largest and most compressible block, which is why it sits in the middle of the priority order rather than at the top.

**Long-term memory** answers "have we seen this before". In support, the answer is usually yes, and a prior resolution is the strongest evidence available — better than a KB article, because it's a fix that actually worked on this problem.

**Short-term memory** is the conversation. It's also the most redundant thing in the window (see compression).

---

## 2. Context Prioritisation

```python
PRIORITY = ["task", "user", "enterprise", "long_term", "short_term"]
```

Lowest index survives longest. Assembly sorts by this, and drops from the bottom.

### The reasoning

**Task and user are structural and never dropped.** An agent without task context doesn't know what it's doing; without user context it doesn't know who it's for. Trimming either doesn't degrade the output — it produces confident work on the wrong problem, which is worse than a truncated answer because it looks fine.

**Enterprise ranks above long-term** because a citation to current documentation beats a similar-looking ticket from March. The KB is maintained; a closed ticket is a snapshot of what was true once.

**Long-term ranks above short-term** because a resolved ticket is signal and a conversation turn is mostly noise. "Any update on this?" occupies tokens and carries nothing.

**Short-term is dropped first** — deliberately, and it feels wrong. Conversation context is what a chatbot would protect above all else. But this is not a chatbot: the ticket body is already in the task prompt, and the thread is largely the customer restating the same problem in rising registers. The information is in the first message and the last, and compression preserves exactly those.

---

## 3. Context Compression Strategy

Two passes, in this order, and the order matters.

### Pass 1 — Compress

Walk the priority list bottom-up, compressing until it fits. `task` and `user` are skipped — compressing them corrupts the run rather than shrinking it.

Compression happens **before** any dropping because shrinking a low-priority block may save enough to keep a high-priority one whole. Dropping first would throw away a block that compression could have accommodated.

### Pass 2 — Drop

Only if compression wasn't enough. Lowest priority first, and every drop is recorded in `AssembledContext.dropped` and logged as a warning. A prompt assembled from less than it asked for is a degradation, and Part 12 counts degradations.

### How compression works

**Truncate to the head, not the tail.** Retrieval returns results ranked by relevance, so the top of the enterprise block is the best evidence and the bottom is the weakest match. Truncating the tail loses exactly what you'd want to lose. Truncating the head would drop the best chunk to keep the fifth-best.

**Short-term uses a different strategy: keep the first turn and the last three.** Support threads are the most redundant text in the system — the customer restates the problem each message, adding frustration but not information. The first turn is the original complaint (with the details later messages assume), and the last three are the current state. The middle is restatement. Explicitly marked: `[... N intermediate turns omitted ...]`, so the agent knows the thread was cut rather than inferring the customer said less than they did.

**No LLM summarisation.** Summarising with a model is the obvious move and it's wrong here. It adds a model call, latency, and cost to every agent invocation — and a second thing that can hallucinate, inside the code path whose entire job is keeping the context faithful. A summariser that drops the one detail the Diagnostic Agent needed is undetectable: the agent doesn't know what it wasn't told. Deterministic truncation is worse on average and much better on the tail, and the tail is where this platform's failures live.

---

## 4. Context Retrieval Strategy

**Scope before you search.** Enterprise retrieval passes `product_area` from `TriageOutput` to Chroma's `where` clause, applied *before* the ANN search. Retrieving top-k globally and filtering after returns fewer than k results and silently starves the agent of evidence — which it then reports as a knowledge gap that doesn't exist. Details in [`RAG.md`](RAG.md).

**Retrieval failure is reported, never swallowed:**

```
(retrieval unavailable: {exc} — do not answer from general knowledge)
```

An empty enterprise block is indistinguishable from a genuine knowledge gap. Handed silence, the agent reports a gap and a Knowledge Manager gets sent to write an article for content that already exists. Handed the failure, it escalates — which is correct, because the system is broken and no answer is available at any confidence.

**Long-term memory is scoped by product area and intent**, capped at 5. Uncapped, a common intent floods the window with near-duplicate tickets and crowds out the KB.

**Retrieval happens per-agent, not once per run.** The Research Agent and the Validation Agent want different things: Research wants breadth to find evidence, Validation wants one specific chunk to verify a claim. A single shared retrieval would serve neither — which is why the Validation Agent has `get_chunk` and not `search_knowledge` (see [`AGENTS.md`](AGENTS.md)).

---

## 5. The Injection Boundary

Every block is rendered wrapped and named:

```
<enterprise>
[#a1b2c3 | exports.pdf p12 — Timeout Behaviour | score 0.847]
An export exceeding 30 minutes is terminated...
</enterprise>
```

This is not formatting. Ticket bodies and retrieved documents are **untrusted input** — a customer can write anything into a ticket, and a document can contain anything. Wrapping and naming each block means a document containing "ignore previous instructions" arrives as *the contents of `<enterprise>`*, not as a new instruction.

Templates are filled by the workflow layer using `str.format`. **An LLM never fills a template.** That boundary is what keeps data as data.

---

## 6. Budget

`DEFAULT_BUDGET = 8_000` tokens.

Sized for a 128k-context model with deliberate slack. The budget is not the context limit — it leaves room for the response and for CrewAI's own scaffolding (role, goal, backstory, tool schemas, ReAct formatting), which is not free and is easy to forget when reasoning about "how much fits."

Measured with `tiktoken`, the same tokeniser the embedding model uses. Character-based estimation drifts by an order of magnitude between prose and code, and support documentation contains both.

---

## 7. Verified Behaviour

Tested in `workflows/context.py`:

1. All five sources assemble
2. User context reflects role authority (`lead` → triage overrides; unassigned → Tier-1 default)
3. Long-term memory scopes by product area and intent
4. Short-term compression keeps first + last three, marks the gap
5. Priority order respected: `task` and `user` come first
6. Under budget pressure, `short_term` → `long_term` → `enterprise` drop in that order; `task` and `user` survive
7. Total tokens stay within budget
8. Every block renders delimited (injection boundary)
9. Under budget, nothing is compressed or dropped
10. Retrieval failure surfaces in-context with an explicit instruction not to answer from priors

---

## 8. What This Doesn't Do

**No vector memory of past conversations.** Long-term memory is a SQL query on structured ticket fields, not semantic search over history. For this corpus, `product_area` + `intent` is a better filter than embedding similarity — the fields are already accurate, and similarity over ticket prose mostly retrieves tickets that *sound* alike rather than tickets that *are* alike.

**No cross-run memory.** Each run assembles context fresh. Runs are independent by design: one ticket's context leaking into another is a data-isolation bug, not a feature.

**No adaptive budget.** 8,000 tokens regardless of model. A per-model budget would be better and is a config change, not a redesign.
