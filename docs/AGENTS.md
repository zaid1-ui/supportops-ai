# Multi-Agent System Design

Seven specialised agents. Each has one job, one output schema, and one set of failure modes it is designed against.

**Code:** `agents/definitions/` · **Schemas:** `agents/schemas.py` · **Prompts:** `agents/prompts/`, documented in [`PROMPT_LIBRARY.md`](PROMPT_LIBRARY.md)

---

## Design Principles

**One agent, one job.** An agent that both retrieves evidence and decides what to do with it cannot be evaluated — a bad outcome could be a retrieval failure or a judgement failure, and there is no way to tell. Separating them makes each failure attributable, which is what the evaluation harness in Part 13 depends on.

**Typed handoffs, not free text.** Every task declares `output_pydantic`. Agents exchange validated objects (`agents/schemas.py`), never prose. A malformed handoff fails at the schema boundary instead of silently corrupting the next agent's reasoning.

**No worker delegates.** Every worker sets `allow_delegation=False`; only the manager in the hierarchical crew delegates. Mutual delegation between workers produces loops, and a reviewer that can delegate would hand work back to the author it is meant to be checking.

**Adversarial validation.** The Validation Agent is instructed to be biased toward FAIL and is forbidden from rewriting drafts. A validator that helps fix a draft becomes a co-author and stops being a check.

**Model tier follows the job.** Classification and scoring run on the fast tier at `temperature=0.0` — reproducibility matters because the eval harness must measure quality, not sampling noise. Analysis and drafting run on the reasoning tier at `0.2`.

---

## 1. Triage Agent

**Role:** Support Triage Specialist · **Tier:** fast · **max_iter:** 3 · `agents/definitions/triage.py`

### Responsibilities
- Classify intent, severity, and product area on every incoming ticket.
- Route to a queue using the fixed routing table.
- Report calibrated confidence so ambiguous tickets reach a human.

Severity sets the SLA clock, which makes this the highest-leverage classification in the platform. Everything downstream inherits its error.

### Inputs
| Field | Source |
|---|---|
| `subject`, `body`, `customer_email` | Ticket record |
| `account_tier` | Ticket record |
| `product_areas` | Enterprise context — the valid taxonomy |

### Outputs
`TriageOutput` — `intent`, `severity`, `product_area`, `queue`, `summary`, `confidence`, `reasoning`

### Tools
`ticket_db_mcp` (read ticket, write classification back)

### Prompt Design
The severity rubric is stated as literal conditions, not adjectives ("service is down or data lost", not "critical"). Adjectives get interpreted against the customer's tone; conditions get checked against the ticket.

The backstory names both failure directions and their costs — under-classifying delays a response someone is losing money over, over-classifying burns senior time and desensitises the team to real S1s — then explicitly refuses to bias toward either. Prompts that warn against only one error reliably produce the opposite error.

Confidence is framed as "your honest probability that this classification survives human review," which anchors it to an observable event rather than a feeling, and the prompt states that low confidence routes to a human and is a correct outcome. Without that, the model treats low confidence as self-criticism and inflates it.

### Failure Modes
| Failure | Cause | Mitigation |
|---|---|---|
| **Severity inflation from tone** | Angry customer reads as S1 | Rubric requires the ticket to *state* an outage; backstory separates tone from severity |
| **Overconfidence** | Models report ~0.9 by default | Confidence anchored to human review; `<0.6` triggers the HITL gate, so miscalibration is caught not fatal |
| **Invented product area** | Ticket fits no known area | Must select from supplied taxonomy or emit `"unknown"` and lower confidence |
| **Routing improvisation** | Model "improves" the routing table | Table declared first-match-wins with an explicit instruction not to improve on it; rationale must name the matched rule |
| **Prompt injection via ticket body** | Hostile customer text | Ticket wrapped in `<ticket>` delimiters; body is data, never instruction |

---

## 2. Research Agent

**Role:** Knowledge Research Analyst · **Tier:** reasoning · **max_iter:** 8 · `agents/definitions/research.py`

### Responsibilities
- Retrieve cited evidence from the knowledge base and prior tickets.
- Reformulate and re-search when the first attempt misses.
- Declare an explicit knowledge gap when the KB genuinely lacks an answer.

Does **not** answer, diagnose, or draft. It hands facts to agents that do.

### Inputs
| Field | Source |
|---|---|
| `summary` | `TriageOutput.summary` |
| `intent`, `product_area` | `TriageOutput` — scopes retrieval |

### Outputs
`ResearchOutput` — `evidence[]` (each a claim + citation), `similar_ticket_ids[]`, `knowledge_gap`, `gap_description`

### Tools
`knowledge_retrieval_mcp` (vector search over enterprise knowledge), `ticket_db_mcp` (similar resolved tickets)

### Prompt Design
`max_iter=8` is the highest in the crew, and deliberately so: the prompt requires reformulation on a miss, and reformulation needs iterations. The specific instruction to try both the customer's phrasing and the product's own terminology targets the most common source of false gaps — vocabulary mismatch between how users describe a problem and how documentation names it.

The gap instruction is written to make declaring a gap *attractive*: it is called a real deliverable that feeds the Knowledge Gap workflow, and explicitly "never a failure on your part." Models treat "I found nothing" as underperformance and will stretch a loosely-related document to avoid it. The prompt names that exact temptation and forbids it, with the reason given — a near-miss presented as evidence is worse than a gap because downstream agents cannot tell it is a near-miss.

The rule "if you cannot cite it, do not return it" is stated as a hard filter rather than a preference, because a partially-cited evidence list is indistinguishable from a fully-cited one at the next agent's input.

### Failure Modes
| Failure | Cause | Mitigation |
|---|---|---|
| **Fabricated evidence** | No results, pressure to produce | Every `Evidence` requires a `Citation`; the schema cannot represent an uncited claim |
| **False knowledge gap** | Vocabulary mismatch, single query | Reformulation mandated; `max_iter=8`; both vocabularies required |
| **Near-miss as answer** | Reluctance to report nothing | Named explicitly in the prompt; gap reframed as a deliverable |
| **Retrieved-but-irrelevant** | Vector search returns top-k regardless of relevance | Metadata scoping by `product_area`; Validation re-checks grounding downstream |
| **Scope creep into diagnosis** | Model wants to be helpful | Backstory states other agents do that and depend on facts, not impressions |

---

## 3. Diagnostic Agent

**Role:** Support Diagnostic Engineer · **Tier:** reasoning · **max_iter:** 5 · `agents/definitions/diagnostic.py`

### Responsibilities
- Reason from symptoms plus evidence to a probable root cause.
- Record and justify the alternatives it rejected.
- Report what information would confirm or refute the hypothesis.

### Inputs
| Field | Source |
|---|---|
| `summary` | `TriageOutput` |
| `evidence` | `ResearchOutput.evidence` |
| `similar_tickets` | `ResearchOutput.similar_ticket_ids` |

### Outputs
`DiagnosticOutput` — `hypothesis`, `supporting_evidence[]`, `alternatives_considered[]`, `confidence`, `missing_information[]`

### Tools
`knowledge_retrieval_mcp` (follow-up lookups), `analytics_mcp` (incident correlation)

### Prompt Design
The procedure is ordered to force elimination before selection: list reported symptoms, propose candidates, test each against evidence, discard contradicted ones, select the survivor. Asking directly for a root cause produces the first plausible story; asking for candidates and then elimination produces a hypothesis with a rejection trail. `alternatives_considered` exists partly as output and partly to make the elimination step observable — an empty list is itself a signal.

Step 1 says "not what you infer, what they said," because symptom lists drift into interpretation immediately and everything downstream then reasons about a problem the customer never reported.

Confidence has numeric anchors rather than adjectives: `>0.8` requires direct evidence, two equally-fitting candidates cap at `0.5`, empty evidence forces `0.0`. The correlation-is-not-causation instruction is concrete — "a log line appearing near an error is not the cause of the error" — because the abstract version is a slogan models agree with and ignore.

"Do not reason from general software knowledge — this product is not like other products" is the load-bearing line. A reasoning model's default move on thin evidence is to substitute its priors about how software generally behaves, which produces confident, fluent, wrong diagnoses.

### Failure Modes
| Failure | Cause | Mitigation |
|---|---|---|
| **Confident diagnosis on no evidence** | Model falls back on general priors | Empty evidence forces `confidence=0.0`; prior-substitution named and forbidden |
| **First-plausible-cause lock-in** | No elimination step | Ordered procedure; `alternatives_considered` must be populated |
| **Correlation as causation** | Co-occurring signals | Concrete instruction; hypotheses resting on such links must self-flag and lower confidence |
| **Symptom drift** | Inference blends into observation | Step 1 constrained to reported text only |
| **Confidence/evidence mismatch** | Fluency mistaken for certainty | Numeric anchors tie the number to evidence class |

---

## 4. Resolution Agent

**Role:** Support Resolution Specialist · **Tier:** reasoning · **max_iter:** 5 · `agents/definitions/resolution.py`

### Responsibilities
- Choose the action: reply, reply-and-close, request info, or escalate.
- Draft the customer-facing reply with citations.
- Record uncertainty in an internal note for the human reviewer.

### Inputs
| Field | Source |
|---|---|
| `subject`, `body` | Ticket record |
| `hypothesis`, `confidence`, `missing_information` | `DiagnosticOutput` |
| `evidence` | `ResearchOutput` |
| `policies` | Enterprise context |

### Outputs
`ResolutionOutput` — `action`, `draft_response`, `citations[]`, `internal_note`, `policy_refs[]`

### Tools
`knowledge_retrieval_mcp`, `email_mcp` (draft only — sending is post-approval and never the agent's call)

### Prompt Design
The four actions are defined by their triggering condition, not by name, so selection is a lookup rather than a vibe. `REQUEST_INFO` and `ESCALATE` are stated to be correct outcomes, because the model's default is to produce a confident answer regardless of whether it has grounds for one.

The anti-padding instruction is specific to the point of quoting the phrase to avoid — "we sincerely apologise for any inconvenience this may have caused." General instructions to "be concise" do not survive contact with a support-email prior; a named, banned phrase does. The rationale is given ("customers want their issue fixed, not sympathised with") because instructions with reasons hold up better under paraphrase pressure.

`internal_note` is the release valve. Without a place to put uncertainty, hedging leaks into the customer draft and makes it useless. The prompt says the note is never sent and instructs bluntness, which lets the draft stay clean while the reviewer still sees the doubt.

"If action is REQUEST_INFO, ask only for what you need and explain why" encodes an operational fact: specific requests get answered, vague ones get ignored, and each ignored request costs a full round trip.

### Failure Modes
| Failure | Cause | Mitigation |
|---|---|---|
| **Ungrounded claim in draft** | Gap-filling with plausible behaviour | Every claim must cite; Validation Agent re-checks independently |
| **Over-promising** | Wanting to satisfy the customer | Policies supplied in context; `policy_refs` required; Validation checks policy |
| **Corporate padding** | Support-email prior in training data | Specific banned phrase, not a general concision instruction |
| **False confidence** | Reluctance to admit uncertainty | `internal_note` absorbs hedging; unknowns must be stated in-draft |
| **Answering on thin evidence** | Default is always to answer | `REQUEST_INFO` / `ESCALATE` framed as correct outcomes |
| **Autonomous send** | — | Structurally impossible: `email_mcp` drafts only; send requires an approval row |

---

## 5. Validation Agent

**Role:** Response Quality Reviewer · **Tier:** reasoning · **max_iter:** 4 · `agents/definitions/validation.py`

### Responsibilities
- Check groundedness, policy compliance, completeness, tone/safety — independently.
- Return PASS or FAIL with an actionable critique.
- Never rewrite the draft.

The last automated check before a human sees the draft.

### Inputs
| Field | Source |
|---|---|
| `body` | Original ticket — for completeness checking |
| `draft_response`, `citations` | `ResolutionOutput` |
| `policies` | Enterprise context |

### Outputs
`ValidationOutput` — `verdict`, `grounded`, `policy_compliant`, `complete`, `issues[]`, `critique`

### Tools
`knowledge_retrieval_mcp` (verify a citation says what it is claimed to say)

### Prompt Design
The asymmetry is stated numerically rather than left implicit: a false PASS reaches a customer, a false FAIL costs one retry loop, and the prompt says these are not symmetrical and must not be treated as such. A validator given no bias defaults to agreeable.

Groundedness is decomposed into claim-by-claim extraction rather than a holistic judgement, because holistic grounding checks pass fluent text. The three failure conditions are enumerated — no citation, citation that does not actually say this, true-in-general-but-unsupported-here — with the third being the one a naive check misses entirely.

"If you find yourself thinking 'that's probably right,' it is ungrounded — flag it" converts the model's own agreement reflex into a detection signal. "Fluency is not evidence; a well-written wrong answer is the exact thing you exist to catch" names the specific bias the agent must resist.

The four checks are ordered and explicitly independent — "do not let a pass on one excuse a fail on another" — because a draft that is well-grounded tends to get waved through on completeness.

`critique` requirements are shown by contrast: "Not grounded" versus "The claim that exports retry automatically has no supporting citation; either cite it or remove it." The critique is the only thing the Resolution Agent receives, so it must stand alone.

### Failure Modes
| Failure | Cause | Mitigation |
|---|---|---|
| **Rubber-stamping** | Agreeableness | FAIL bias stated with the cost asymmetry spelled out |
| **Fluency mistaken for grounding** | Well-written text reads as correct | Claim-by-claim extraction; fluency named as the bias to resist |
| **Missing true-but-unsupported claims** | Model knows it is true generally | Enumerated as a distinct failure condition |
| **Becoming a co-author** | Fixing instead of flagging | "Do not rewrite"; `allow_delegation=False`; schema has no draft field |
| **Vague critique → retry loop** | Non-actionable feedback | Good/bad contrast in the prompt; `offending_text` required |
| **Infinite retry** | Repeated FAIL | Workflow caps at 2 retries, then escalates to a human |

---

## 6. Escalation Agent

**Role:** Escalation Risk Analyst · **Tier:** fast · **max_iter:** 3 · `agents/definitions/escalation.py`

### Responsibilities
- Score SLA, churn, and complexity risk.
- Decide whether a human tier is needed now.
- Name the drivers that actually moved the score.

### Inputs
| Field | Source |
|---|---|
| `severity`, `account_tier`, `age_hours`, `sla_hours` | Ticket record |
| `reopen_count`, `message_count`, `latest_message` | Ticket thread |
| `action`, `confidence` | `ResolutionOutput`, `DiagnosticOutput` |

### Outputs
`EscalationOutput` — `risk_level`, `risk_score`, `drivers[]`, `escalate`, `target_queue`, `rationale`

### Tools
`ticket_db_mcp`, `analytics_mcp` (historical breach patterns)

### Prompt Design
Drivers are supplied as a weighted list with interpretation attached rather than raw fields. `reopen_count` is the clearest case: the prompt states that one reopen means the last answer was wrong and two means the process is failing, not the answer. That distinction changes the routing target, and the model will not derive it from the number alone.

"Sentiment trajectory... not how loud the latest one is" and the flat rule "tone alone never justifies escalation — a furious customer with a password reset is a password reset" both exist because sentiment is the most available signal in the context and the least predictive one. Without an explicit rule, the model escalates on volume and the Tier-2 queue fills with routine work.

`drivers` must list only factors that actually moved the score. Models pad such lists with every input they were given, which makes the output unusable for the team lead who needs to know *why* this ticket surfaced.

The asymmetry here is the reverse of Triage's: escalation is expensive, a missed escalation is more expensive, so uncertainty resolves toward escalating.

### Failure Modes
| Failure | Cause | Mitigation |
|---|---|---|
| **Escalating on tone** | Sentiment is salient | Flat rule with a concrete counterexample; trajectory over volume |
| **Missing quiet risk** | No emotional signal | SLA proximity weighted as the strongest single driver, independent of tone |
| **Driver padding** | Listing all inputs | Only score-moving factors permitted, strongest first |
| **Under-escalating S1** | Other factors dilute | `S1` always escalates, stated as absolute |
| **Escalation as an out** | Escalating everything | Cost stated; `escalate=True` requires a rationale naming drivers |

---

## 7. Reporting Agent

**Role:** Support Operations Analyst · **Tier:** reasoning · **max_iter:** 5 · `agents/definitions/reporting.py`

### Responsibilities
- Generate RCA reports, knowledge gap backlogs, and risk registers.
- Lead with findings; end with owned recommendations.

### Inputs
| Field | Source |
|---|---|
| `report_type` | Workflow |
| `data` | Workflow state, analytics, gap flags |

### Outputs
`ReportingOutput` — `title`, `executive_summary`, `sections[]`, `recommendations[]`, `citations[]`

### Tools
`analytics_mcp`, `report_generation_mcp`, `knowledge_retrieval_mcp`

### Prompt Design
"Lead with the finding, not the methodology" fights the report-shaped prior in training data, which opens with background and buries conclusions. The executive summary is capped at 120 words and the audience is named — a director who will read the summary, glance at recommendations, and act.

Recommendation quality is specified by contrast rather than adjective: "improve documentation" is rejected, "add a KB article covering CSV export timeouts for exports over 50k rows — Knowledge Manager" is the standard. Every recommendation needs a specific action and an owner, or it will not be actioned.

"Report what the data shows, including where the platform performed badly. An honest negative finding is the most useful thing you produce" — an agent reporting on its own platform's performance will otherwise soften bad numbers.

### Failure Modes
| Failure | Cause | Mitigation |
|---|---|---|
| **Methodology-first** | Report prior | Finding-first mandated; 120-word cap forces it |
| **Vague recommendations** | Generic advice is easy | Good/bad contrast; action + owner required |
| **Self-flattery** | Reporting on its own system | Honest negatives explicitly demanded |
| **Uncited figures** | Numbers from workflow state feel like facts | `citations[]` required for every quoted figure |
| **Length inflation** | More text reads as more thorough | Word cap; audience named |

---

## Crew Composition

| Agent | Tier | Temp | `max_iter` | Delegation | Primary schema |
|---|---|---|---|---|---|
| Triage | fast | 0.0 | 3 | ✗ | `TriageOutput` |
| Research | reasoning | 0.2 | 8 | ✗ | `ResearchOutput` |
| Diagnostic | reasoning | 0.2 | 5 | ✗ | `DiagnosticOutput` |
| Resolution | reasoning | 0.2 | 5 | ✗ | `ResolutionOutput` |
| Validation | reasoning | 0.2 | 4 | ✗ | `ValidationOutput` |
| Escalation | fast | 0.0 | 3 | ✗ | `EscalationOutput` |
| Reporting | reasoning | 0.2 | 5 | ✗ | `ReportingOutput` |

Orchestration — crew assembly, delegation, state management, error recovery — is Part 3.
