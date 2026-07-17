"""Task prompts.

CrewAI renders `Task.description` after the agent's backstory. These templates
are the task layer: what to do *now*, given this specific input.

Formatting contract: every template uses `str.format`-style named placeholders
and is filled by the workflow layer, never by an LLM.
"""

# ---------------------------------------------------------------------------
# Routing prompts — classification and dispatch decisions
# ---------------------------------------------------------------------------

TRIAGE_TASK = """\
Classify the support ticket below.

<ticket>
Subject: {subject}
From: {customer_email}
Account tier: {account_tier}
Body:
{body}
</ticket>

<product_areas>
{product_areas}
</product_areas>

Severity rubric — apply literally, do not interpolate:
- S1: Service is down, or data has been lost. Affects many users or is
      unrecoverable for one. The SLA clock is measured in minutes.
- S2: A major feature is broken with no workaround. One customer is blocked.
- S3: A feature is degraded or behaves incorrectly, but a workaround exists.
- S4: A question, a cosmetic defect, or a feature request. Nothing is broken.

Rules:
- Classify only what the ticket says. If the customer does not say the service
  is down, it is not S1, however urgent their tone.
- product_area must be chosen from the list above. If none fit, use "unknown"
  and lower your confidence.
- confidence is your honest probability that this classification survives human
  review. Below 0.6 routes the ticket to a human, which is the correct outcome
  for a genuinely ambiguous ticket. Do not inflate it.

Return a TriageOutput.
"""


ROUTING_TASK = """\
Select the queue for this classified ticket.

<classification>
Intent: {intent}
Severity: {severity}
Product area: {product_area}
</classification>

Routing table — apply in order, first match wins:
1. severity is S1                  -> engineering
2. intent is billing               -> billing
3. intent is account_access        -> tier_1
4. severity is S2                  -> tier_2
5. anything else                   -> tier_1

Apply the table exactly. It encodes staffing decisions you do not have context
for, so do not improve on it.

Return the queue and a one-sentence rationale naming the rule you matched.
"""


# ---------------------------------------------------------------------------
# Task prompts — the core work
# ---------------------------------------------------------------------------

RESEARCH_TASK = """\
Find evidence that answers the ticket below.

<ticket>
{summary}
</ticket>

<classification>
Intent: {intent}
Product area: {product_area}
</classification>

Procedure:
1. Search the knowledge base with knowledge_retrieval. Scope by product_area.
2. Search prior tickets with ticket_db for resolved cases with these symptoms.
3. If the first search returns nothing useful, reformulate and search again.
   Try the customer's phrasing and the product's own terminology — they often
   differ, and that mismatch is a common cause of a false gap.

For each fact you return:
- `claim` is a single statement, drawn from the source and nothing else.
- `citation` points to the chunk it came from.
- If you cannot cite it, do not return it.

Deciding knowledge_gap:
- Set True when repeated, well-formed searches return nothing that answers the
  question.
- Set True rather than returning a loosely-related document as though it
  answered the question. A near-miss presented as evidence is worse than a gap,
  because downstream agents cannot tell it is a near-miss.
- When True, `gap_description` states specifically what content is missing.

Return a ResearchOutput.
"""


DIAGNOSTIC_TASK = """\
Determine the probable root cause.

<ticket>
{summary}
</ticket>

<evidence>
{evidence}
</evidence>

<similar_resolved_tickets>
{similar_tickets}
</similar_tickets>

Procedure:
1. List the symptoms the customer actually reported. Not what you infer, what
   they said.
2. Propose candidate causes consistent with those symptoms.
3. Test each against the evidence. Discard those the evidence contradicts.
4. Select the most probable survivor as your hypothesis.
5. Record the discarded candidates in alternatives_considered with the reason.

Calibration:
- confidence > 0.8 requires direct evidence, not a plausible story.
- If two candidates fit equally well, confidence must not exceed 0.5.
- If the evidence is empty, say so and return confidence 0.0. Do not reason from
  general software knowledge — this product is not like other products.

missing_information lists what the customer must supply to confirm the
hypothesis. This is what the Resolution Agent will ask for.

Return a DiagnosticOutput.
"""


RESOLUTION_TASK = """\
Decide the action and draft the customer reply.

<ticket>
Subject: {subject}
Body: {body}
</ticket>

<diagnosis>
Hypothesis: {hypothesis}
Confidence: {confidence}
Missing information: {missing_information}
</diagnosis>

<evidence>
{evidence}
</evidence>

<policies>
{policies}
</policies>

Choose the action:
- REPLY_AND_CLOSE  — the evidence fully answers the ticket, nothing is pending.
- REPLY_ONLY       — you can help, but the customer will likely need follow-up.
- REQUEST_INFO     — missing_information is non-empty and blocks a real answer.
- ESCALATE         — no evidence, or the fix needs authority you do not have.

Draft rules:
- Open with one sentence naming the customer's actual problem. Then solve it.
- No apology paragraph. No "we value your business." No filler.
- Numbered steps for anything procedural.
- Every factual claim traces to a citation. List those citations.
- State what is still unknown, when something is.
- If action is REQUEST_INFO, ask only for what you need and explain why you
  need it. Customers comply with specific requests and ignore vague ones.

internal_note is for the human reviewer. Put your uncertainty there: what you
were unsure about, what you would check, what might be wrong. This note is never
sent to the customer, so be blunt in it.

Return a ResolutionOutput.
"""


# ---------------------------------------------------------------------------
# Validation prompts — the quality gate
# ---------------------------------------------------------------------------

VALIDATION_TASK = """\
Review this draft. Do not rewrite it.

<customer_ticket>
{body}
</customer_ticket>

<draft_response>
{draft_response}
</draft_response>

<citations_supplied>
{citations}
</citations_supplied>

<policies>
{policies}
</policies>

Run these four checks independently. Do not let a pass on one excuse a fail on
another.

1. GROUNDEDNESS
   Extract every factual claim in the draft, one by one. For each, find the
   citation that supports it. A claim is ungrounded if:
   - no supplied citation supports it, or
   - a citation exists but does not actually say this, or
   - it is true in general but unsupported for this product.
   Plausibility is not grounding. If you find yourself thinking "that's probably
   right," it is ungrounded — flag it.

2. POLICY
   Does the draft promise anything the policies do not permit? Refunds,
   timelines, guarantees, roadmap commitments. An unpermitted promise is a FAIL
   even if the customer would be delighted by it.

3. COMPLETENESS
   Did the customer ask more than one question? Answer each one. A draft that
   answers the interesting question and ignores the boring one is incomplete.

4. TONE AND SAFETY
   Is it defensive, condescending, or blaming the customer? Does it disclose
   internal systems, other customers, or security detail?

Verdict:
- Any ungrounded claim  -> FAIL.
- Any policy violation  -> FAIL.
- Unanswered question   -> FAIL.
- Otherwise             -> PASS.

On FAIL, `critique` must name the exact defect and the fix. Quote the offending
span in offending_text. The Resolution Agent gets only your critique, not your
reasoning, so the critique must stand alone.

Return a ValidationOutput.
"""


# ---------------------------------------------------------------------------
# Escalation prompts
# ---------------------------------------------------------------------------

ESCALATION_TASK = """\
Score the escalation risk for this ticket.

<ticket>
Severity: {severity}
Account tier: {account_tier}
Age (hours): {age_hours}
SLA target (hours): {sla_hours}
Reopen count: {reopen_count}
Message count: {message_count}
</ticket>

<latest_customer_message>
{latest_message}
</latest_message>

<resolution_state>
Action: {action}
Diagnostic confidence: {confidence}
</resolution_state>

Weigh these drivers:
- SLA proximity. Past 75% of target with no resolution is the strongest single
  signal.
- Reopen count. A reopened ticket means the last answer was wrong. Two reopens
  means the process is failing, not the answer.
- Message count. A long thread signals the issue is not understood.
- Account tier. Enterprise accounts carry contractual response terms.
- Sentiment trajectory. Whether frustration is rising across messages, not how
  loud the latest one is.
- Diagnostic confidence. Low confidence plus high severity is a bad pair.

Rules:
- Tone alone never justifies escalation. A furious customer with a password
  reset is a password reset. Escalate on trajectory, not volume.
- S1 always escalates, regardless of every other factor.
- When genuinely uncertain, escalate and say so in the rationale.

`drivers` lists the factors that actually moved your score, strongest first. Do
not list factors that did not matter.

Return an EscalationOutput.
"""


# ---------------------------------------------------------------------------
# Reporting prompts
# ---------------------------------------------------------------------------

REPORTING_TASK = """\
Write a {report_type} report.

<data>
{data}
</data>

Structure:
- title
- executive_summary: what a director needs, in under 120 words. The finding
  first, never the methodology.
- sections: the supporting detail.
- recommendations: specific, actionable, owned. "Improve documentation" is not
  a recommendation. "Add a KB article covering CSV export timeouts for exports
  over 50k rows — Knowledge Manager" is.
- citations: sources for every figure you quote.

Report what the data shows, including where the platform performed badly. An
honest negative finding is the most useful thing you produce.

Return a ReportingOutput.
"""
