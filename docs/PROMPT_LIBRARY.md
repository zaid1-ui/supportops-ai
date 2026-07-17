# Prompt Library

Production prompts for SupportOps AI, organised by the five categories in Part 4.

**Source:** `agents/prompts/system.py` (system prompts) · `agents/prompts/task.py` (task, routing, validation, escalation prompts)

Prompts live in Python modules and are documented here rather than being duplicated. The modules are the source of truth; this document explains why each one is shaped the way it is.

---

## Layering

CrewAI composes three layers into the final context:

```
Agent.backstory   →  system prompt   (identity, constraints, refusals)
Task.description  →  task prompt     (what to do now, with this input)
output_pydantic   →  output contract (schema, injected by CrewAI)
```

`SHARED_RULES` is prepended to every backstory so the platform-wide rules are stated once. Duplicating them per agent guarantees drift — someone edits five of seven and the two stragglers quietly diverge.

Task prompts use `str.format` placeholders filled by the workflow layer. **An LLM never fills a template.** That boundary is what keeps retrieved documents and customer text as data rather than instructions.

---

## Cross-Cutting Design Rules

These recur throughout the library and are worth stating once.

**Name the failure, then forbid it.** "Be accurate" is unenforceable. "A near-miss presented as evidence is worse than a gap, because downstream agents cannot tell it is a near-miss" is. Every constraint that matters names the specific thing going wrong and why it is bad.

**Give reasons.** Instructions with rationale survive paraphrase pressure; bare imperatives get optimised away when they conflict with a strong prior.

**Specify by contrast, not adjective.** "Be specific" produces nothing. Showing "improve documentation" against "add a KB article covering CSV export timeouts for exports over 50k rows — Knowledge Manager" produces the second.

**State both failure directions.** A prompt warning against only one error reliably produces the opposite. Triage names inflation *and* deflation; Validation names false-PASS *and* false-FAIL, with their costs.

**Anchor numbers to observables.** "Confidence" alone is a feeling. "Your honest probability that this classification survives human review" is a prediction about an event that actually happens.

**Delimit untrusted input.** Ticket bodies and retrieved documents are wrapped in XML-ish tags. The model is told these are data. This is the injection boundary.

**Make the correct-but-unsatisfying answer attractive.** Models treat "I found nothing" as failure and will manufacture an answer to avoid it. Every prompt where that applies explicitly reframes the null result as a deliverable.

---

# 1. System Prompts

Rendered ahead of every task. Establish identity, hard constraints, refusal conditions.

## 1.1 `SHARED_RULES`

**Purpose** — The five non-negotiable platform rules, prepended to all seven backstories.

**Design reasoning**

Rule 1 (grounding) says "You have no reliable independent knowledge of this product." Stronger than "cite your sources," and aimed at the actual failure: a model's product knowledge is a plausible-sounding average of every SaaS product in training, which is exactly wrong here.

Rule 2 (admit gaps) states that fabrication is *the single worst failure available* and says why — a confident wrong answer reaches a customer. Ranking the failure explicitly matters; models trade off silently otherwise, and helpfulness usually wins.

Rule 3 (no customer contact) is stated even though it is enforced structurally by the approval gate. Agents that believe they are talking to a customer write differently — more hedging, more apology — than agents writing for a reviewer. This is about register, not permission.

Rule 4 (stay in role) exists because helpful models bleed across role boundaries: Research starts diagnosing, Validation starts drafting. That collapses the separation the whole architecture depends on.

Rule 5 (structured output) suppresses the chat-assistant prior of wrapping JSON in prose and markdown fences.

**Expected output** — No output of its own. Constrains all seven agents.

## 1.2 Agent Backstories

| Constant | Agent | Core move |
|---|---|---|
| `TRIAGE_BACKSTORY` | Triage | Names both failure directions with costs; refuses to bias either way |
| `RESEARCH_BACKSTORY` | Research | Reframes the knowledge gap as a deliverable, not a personal failure |
| `DIAGNOSTIC_BACKSTORY` | Diagnostic | Hypothesis, not verdict; confidence must track evidence |
| `RESOLUTION_BACKSTORY` | Resolution | Bans the specific apology phrasing; partial answers are legitimate |
| `VALIDATION_BACKSTORY` | Validation | Reviewer not collaborator; FAIL bias with cost asymmetry |
| `ESCALATION_BACKSTORY` | Escalation | Trajectory over volume; uncertainty resolves toward escalating |
| `REPORTING_BACKSTORY` | Reporting | Finding first; owned recommendations; honest negatives |

**Expected output** — Behavioural constraint. Detailed per-agent rationale in [`AGENTS.md`](AGENTS.md).

---

# 2. Task Prompts

What to do *now*, given this input.

## 2.1 `RESEARCH_TASK`

**Purpose** — Retrieve cited evidence, or declare a knowledge gap.

**Design reasoning**

Numbered procedure: search scoped by `product_area`, search prior tickets, reformulate on a miss. The reformulation instruction names the specific remedy — try the customer's phrasing *and* the product's terminology, "they often differ, and that mismatch is a common cause of a false gap." Vocabulary mismatch is the dominant false-gap driver, and naming it converts a vague instruction into a checkable step.

The citation rule is a filter, not a preference: "If you cannot cite it, do not return it." A partially-cited evidence list is indistinguishable from a fully-cited one at the next agent's input, so the filter has to bite here or not at all.

The gap section does three things: defines when to set the flag, forbids the near-miss substitution with a reason, and requires a specific `gap_description`. The near-miss clause is the load-bearing one — it names the exact temptation rather than trusting the general honesty instruction to cover it.

**Expected output** — `ResearchOutput`. Either non-empty `evidence[]` with every claim cited, or `knowledge_gap=True` with a populated `gap_description`. Never both empty.

## 2.2 `DIAGNOSTIC_TASK`

**Purpose** — Symptoms plus evidence to a probable root cause with a rejection trail.

**Design reasoning**

Five ordered steps force elimination before selection. Asking directly for a root cause yields the first plausible story; asking for candidates, then testing each against evidence, then discarding the contradicted ones yields a hypothesis that survived something. `alternatives_considered` makes that step observable — an empty list means the elimination did not happen.

Step 1's "not what you infer, what they said" prevents symptom drift, where interpretation silently replaces observation and every downstream agent reasons about a problem the customer never reported.

Calibration is numeric: `>0.8` needs direct evidence, ties cap at `0.5`, empty evidence forces `0.0`. Three anchor points rather than a scale description, because scale descriptions get compressed to "fairly confident."

"Do not reason from general software knowledge — this product is not like other products" is the most important line. A reasoning model's default on thin evidence is to substitute priors about how software behaves generally, producing a confident, fluent, wrong diagnosis. General priors must be named and blocked.

**Expected output** — `DiagnosticOutput`. `confidence=0.0` and an empty hypothesis when evidence is empty.

## 2.3 `RESOLUTION_TASK`

**Purpose** — Choose the action; draft the cited customer reply.

**Design reasoning**

Four actions defined by triggering condition, so selection is a lookup. `REQUEST_INFO` and `ESCALATE` are named correct outcomes, countering the default of answering regardless of grounds.

Draft rules are concrete to the point of quoting the banned phrase — "we sincerely apologise for any inconvenience this may have caused." A general concision instruction does not survive contact with the support-email prior; a named banned phrase does.

`internal_note` is the pressure valve. Given nowhere to put uncertainty, the model hedges inside the customer draft and produces something useless to everyone. Telling it the note is never sent and instructing bluntness keeps the draft clean and gives the reviewer the doubt.

"Ask only for what you need and explain why you need it" encodes an operational fact: vague requests get ignored and each ignored request costs a full round trip.

**Expected output** — `ResolutionOutput`. `citations[]` covers every factual claim. `internal_note` is always populated.

## 2.4 `REPORTING_TASK`

**Purpose** — Turn workflow data into a report a director will act on.

**Design reasoning**

The 120-word summary cap is a forcing function, not a style preference — it makes methodology-first impossible. Audience named explicitly: someone who reads the summary, glances at recommendations, and acts.

Recommendation standard given by contrast. Honest-negatives clause included because an agent reporting on its own platform will otherwise soften bad numbers, which destroys the report's only real function.

**Expected output** — `ReportingOutput`. Every recommendation has an action and an owner; every figure has a citation.

---

# 3. Validation Prompts

## 3.1 `VALIDATION_TASK`

**Purpose** — Gate the draft. PASS or FAIL with an actionable critique.

**Design reasoning**

Opens with "Review this draft. Do not rewrite it." First position because it is the instruction most likely to be violated — a helpful model fixes what it finds.

Four checks, ordered, explicitly independent: "do not let a pass on one excuse a fail on another." Well-grounded drafts otherwise get waved through on completeness.

The groundedness check is decomposed into claim-by-claim extraction. Holistic grounding checks pass fluent text — that is precisely their failure mode. The three failure conditions are enumerated because the third (true in general, unsupported for this product) is invisible to a naive check and is the most dangerous, since it is the one the model itself believes.

"If you find yourself thinking 'that's probably right,' it is ungrounded — flag it" turns the agreement reflex into a detection signal — the model's own assent becomes evidence of the defect. "Fluency is not evidence; a well-written wrong answer is the exact thing you exist to catch" names the bias directly.

Verdict rules are mechanical: any ungrounded claim → FAIL, any policy violation → FAIL, any unanswered question → FAIL. No weighing, no judgement call, no room for "mostly fine."

Critique quality is shown by contrast: "Not grounded" versus "The claim that exports retry automatically has no supporting citation; either cite it or remove it." The Resolution Agent receives only the critique, so it must stand alone.

**Expected output** — `ValidationOutput`. FAIL requires a populated `critique` and at least one `issues[]` entry with `offending_text`.

**Loop control** — Retries capped at 2 in the workflow layer; the third failure escalates to a human. An LLM judging an LLM's revision can loop indefinitely, and the cap lives outside the prompt because a prompt cannot reliably count its own attempts.

---

# 4. Routing Prompts

## 4.1 `TRIAGE_TASK`

**Purpose** — Classify intent, severity, and product area.

**Design reasoning**

The severity rubric is stated as literal conditions — "service is down, or data has been lost" — not adjectives. "Critical" gets interpreted against customer tone; "the service is down" gets checked against the ticket. The rubric is prefaced "apply literally, do not interpolate."

The explicit rule "if the customer does not say the service is down, it is not S1, however urgent their tone" exists because tone is the most salient thing in a ticket and the least informative about severity.

`product_area` is constrained to a supplied taxonomy with `"unknown"` as the escape hatch, paired with lowered confidence. Without a legal escape, the model invents an area, and the invented value silently breaks retrieval scoping downstream.

Confidence is anchored to human review, and the prompt states that below 0.6 routes to a human and that this is correct for a genuinely ambiguous ticket. Told only "report confidence," models report ~0.9 uniformly and the HITL gate never fires.

The ticket is wrapped in `<ticket>` tags — this is the injection boundary for hostile customer text.

**Expected output** — `TriageOutput`. `product_area` from the taxonomy or `"unknown"`. `confidence` calibrated, not inflated.

## 4.2 `ROUTING_TASK`

**Purpose** — Map a classified ticket to a queue.

**Design reasoning**

A deterministic first-match-wins table, not a judgement:

```
1. S1                  -> engineering
2. billing             -> billing
3. account_access      -> tier_1
4. S2                  -> tier_2
5. otherwise           -> tier_1
```

"Apply the table exactly. It encodes staffing decisions you do not have context for, so do not improve on it." Given a table without that instruction, models optimise it — routing an S1 billing issue to billing because it "seems more relevant." The table's order already resolves that: S1 outranks intent, because an outage needs engineers regardless of what it is about.

The rationale must name the matched rule, which makes misrouting diagnosable — you can see which rule the model thought it matched.

This is arguably code rather than a prompt, and the ordering is deliberately trivial to keep it auditable. It stays an agent task so routing appears in the same trace and metrics as every other decision.

**Expected output** — Queue plus a one-sentence rationale naming the rule.

---

# 5. Escalation Prompts

## 5.1 `ESCALATION_TASK`

**Purpose** — Score risk; decide whether a human tier is needed now.

**Design reasoning**

Six drivers supplied with interpretation attached, not as raw fields. `reopen_count` is the clearest case: "A reopened ticket means the last answer was wrong. Two reopens means the process is failing, not the answer." That distinction changes the routing target, and no model derives it from an integer.

SLA proximity is named the strongest single signal, and deliberately: it is objective, and it is the driver least entangled with tone.

Two instructions handle the dominant failure. "Sentiment trajectory. Whether frustration is rising across messages, not how loud the latest one is" reframes the signal. Then the flat rule with a counterexample: "Tone alone never justifies escalation. A furious customer with a password reset is a password reset." Sentiment is the most available signal in the context and among the least predictive; without an explicit rule, Tier-2 fills with routine work and stops trusting escalations.

`S1` always escalates — absolute, no weighing, because dilution across five other factors is exactly how a real S1 gets missed.

`drivers` must contain only score-moving factors, strongest first. Models pad these lists with every input, which makes them useless to the team lead who needs to know why *this* ticket surfaced.

The asymmetry inverts Triage's: escalation is expensive, a missed escalation is more expensive, so uncertainty resolves toward escalating — and the rationale must say so.

**Expected output** — `EscalationOutput`. `escalate=True` requires `target_queue` and a rationale naming the drivers.

---

## Prompt Inventory

| Constant | Category | Agent | Module |
|---|---|---|---|
| `SHARED_RULES` | System | all | `prompts/system.py` |
| `TRIAGE_BACKSTORY` | System | Triage | `prompts/system.py` |
| `RESEARCH_BACKSTORY` | System | Research | `prompts/system.py` |
| `DIAGNOSTIC_BACKSTORY` | System | Diagnostic | `prompts/system.py` |
| `RESOLUTION_BACKSTORY` | System | Resolution | `prompts/system.py` |
| `VALIDATION_BACKSTORY` | System | Validation | `prompts/system.py` |
| `ESCALATION_BACKSTORY` | System | Escalation | `prompts/system.py` |
| `REPORTING_BACKSTORY` | System | Reporting | `prompts/system.py` |
| `TRIAGE_TASK` | Routing | Triage | `prompts/task.py` |
| `ROUTING_TASK` | Routing | Triage | `prompts/task.py` |
| `RESEARCH_TASK` | Task | Research | `prompts/task.py` |
| `DIAGNOSTIC_TASK` | Task | Diagnostic | `prompts/task.py` |
| `RESOLUTION_TASK` | Task | Resolution | `prompts/task.py` |
| `VALIDATION_TASK` | Validation | Validation | `prompts/task.py` |
| `ESCALATION_TASK` | Escalation | Escalation | `prompts/task.py` |
| `REPORTING_TASK` | Task | Reporting | `prompts/task.py` |
