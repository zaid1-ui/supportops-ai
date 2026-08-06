"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { Shell } from "@/components/shell";
import { Trace } from "@/components/trace";
import { Empty, ErrorBox, Loading, PageHeader, Status } from "@/components/ui";

export default function WorkflowsPage() {
  const qc = useQueryClient();
  const [ticketId, setTicketId] = useState("TK-1001");
  const [runId, setRunId] = useState<string | null>(null);

  const workflows = useQuery({
    queryKey: ["workflows"],
    queryFn: api.workflows,
  });
  const [workflow, setWorkflow] = useState("ticket_resolution");

  // ---- Create-ticket form state ----
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState({
    id: "TK-5005",
    subject: "",
    body: "",
    customer_email: "",
    account_tier: "standard",
    sla_hours: "24",
  });

  const create = useMutation({
    mutationFn: () =>
      api.createTicket({
        id: draft.id,
        subject: draft.subject,
        body: draft.body,
        customer_email: draft.customer_email,
        account_tier: draft.account_tier,
        sla_hours: Number(draft.sla_hours),
      }),
    onSuccess: (t) => {
      setTicketId(t.id);
      setShowCreate(false);
      setDraft({
        ...draft,
        id: "TK-5006",
        subject: "",
        body: "",
        customer_email: "",
      });
    },
  });

  // Batch workflows scan the whole queue, so asking for a ticket would be a lie
  // about what the run does.
  const BATCH = ["knowledge_gap_review", "escalation_risk_assessment"];
  const isBatch = BATCH.includes(workflow);

  const status = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.workflowStatus(runId!),
    enabled: !!runId,
    // Poll while in flight; stop once the run is terminal or parked on a human.
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s &&
        ["completed", "failed", "escalated", "awaiting_approval"].includes(s)
        ? false
        : 3_000;
    },
  });

  const start = useMutation({
    mutationFn: () => api.runWorkflow(workflow, ticketId),
    onSuccess: (r) => {
      setRunId(r.run_id);
      qc.invalidateQueries({ queryKey: ["approvals"] });
      qc.invalidateQueries({ queryKey: ["metrics"] });
    },
  });

  return (
    <Shell>
      <PageHeader
        title="Workflows"
        description="Start a run and watch the crew work."
      />

      <div className="card mb-4 flex flex-wrap items-end gap-3 p-4">
        <div className="min-w-[200px]">
          <label htmlFor="wf" className="eyebrow mb-1 block">
            Workflow
          </label>
          <select
            id="wf"
            value={workflow}
            onChange={(e) => setWorkflow(e.target.value)}
            className="input"
          >
            {workflows.data?.map((w) => (
              <option key={w} value={w}>
                {w.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
        {!isBatch && (
          <div className="min-w-[160px]">
            <label htmlFor="tk" className="eyebrow mb-1 block">
              Ticket
            </label>
            <input
              id="tk"
              value={ticketId}
              onChange={(e) => setTicketId(e.target.value)}
              className="input font-mono"
            />
          </div>
        )}
        <button
          onClick={() => start.mutate()}
          disabled={start.isPending}
          className="btn-primary"
        >
          {start.isPending ? "Starting…" : "Start run"}
        </button>
        {!isBatch && (
          <button
            onClick={() => setShowCreate((s) => !s)}
            className="btn-ghost"
          >
            {showCreate ? "Cancel" : "+ Create ticket"}
          </button>
        )}
        <p className="text-xs text-muted">
          {isBatch
            ? "Scans the whole open queue — no ticket needed. Takes minutes and ends at a review gate."
            : "Seeded tickets: TK-1001, TK-1002, TK-1003. Takes minutes and stops at an approval gate."}
        </p>
      </div>

      {showCreate && !isBatch && (
        <div className="card mb-4 p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="eyebrow">Create a ticket</p>
            <span className="text-xs text-faint">
              It lands OPEN in the queue, ready for a run.
            </span>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="tk-id" className="eyebrow mb-1 block">
                ID
              </label>
              <input
                id="tk-id"
                value={draft.id}
                onChange={(e) => setDraft({ ...draft, id: e.target.value })}
                className="input font-mono"
                placeholder="TK-5005"
              />
            </div>
            <div>
              <label htmlFor="tk-sla" className="eyebrow mb-1 block">
                SLA hours
              </label>
              <input
                id="tk-sla"
                type="number"
                min={1}
                max={168}
                value={draft.sla_hours}
                onChange={(e) =>
                  setDraft({ ...draft, sla_hours: e.target.value })
                }
                className="input"
              />
            </div>
            <div className="md:col-span-2">
              <label htmlFor="tk-subject" className="eyebrow mb-1 block">
                Subject
              </label>
              <input
                id="tk-subject"
                value={draft.subject}
                onChange={(e) =>
                  setDraft({ ...draft, subject: e.target.value })
                }
                className="input"
                placeholder="Cannot access API dashboard"
              />
            </div>
            <div className="md:col-span-2">
              <label htmlFor="tk-body" className="eyebrow mb-1 block">
                Body
              </label>
              <textarea
                id="tk-body"
                value={draft.body}
                onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                className="input min-h-[90px]"
                placeholder="Describe the customer's problem…"
              />
            </div>
            <div>
              <label htmlFor="tk-email" className="eyebrow mb-1 block">
                Customer email
              </label>
              <input
                id="tk-email"
                value={draft.customer_email}
                onChange={(e) =>
                  setDraft({ ...draft, customer_email: e.target.value })
                }
                className="input"
                placeholder="dev@acme.example"
              />
            </div>
            <div>
              <label htmlFor="tk-tier" className="eyebrow mb-1 block">
                Account tier
              </label>
              <select
                id="tk-tier"
                value={draft.account_tier}
                onChange={(e) =>
                  setDraft({ ...draft, account_tier: e.target.value })
                }
                className="input"
              >
                <option value="standard">standard</option>
                <option value="enterprise">enterprise</option>
                <option value="growth">growth</option>
              </select>
            </div>
          </div>
          {create.error != null && <ErrorBox error={create.error} />}
          <div className="mt-3 flex justify-end gap-2">
            <button onClick={() => setShowCreate(false)} className="btn-ghost">
              Cancel
            </button>
            <button
              onClick={() => create.mutate()}
              disabled={
                create.isPending ||
                !draft.subject ||
                !draft.body ||
                !draft.customer_email
              }
              className="btn-primary"
            >
              {create.isPending ? "Creating…" : "Create ticket"}
            </button>
          </div>
        </div>
      )}

      {start.error != null && <ErrorBox error={start.error} />}
      {!runId && (
        <Empty
          title="No run selected"
          hint="Start a run above to see its trace here."
        />
      )}

      {runId && (
        <div className="space-y-4">
          <div className="card flex flex-wrap items-center gap-3 p-4">
            <Status value={status.data?.status ?? "pending"} />
            <span className="font-mono text-micro text-faint">
              run {runId.slice(0, 8)}
            </span>
            {status.data?.current_task && (
              <span className="chip bg-signal-soft text-signal">
                {status.data.current_task}
              </span>
            )}
            {status.data?.status === "awaiting_approval" && (
              <a href="/approvals" className="btn-primary ml-auto">
                Review in Approvals
              </a>
            )}
          </div>

          {status.data?.error && (
            <ErrorBox error={new Error(status.data.error)} />
          )}

          <div className="card">
            <div className="border-b border-line px-4 py-2.5">
              <p className="eyebrow">Trace</p>
            </div>
            {status.isLoading ? (
              <Loading label="Loading trace" />
            ) : (
              <Trace events={status.data?.events ?? []} />
            )}
          </div>
        </div>
      )}
    </Shell>
  );
}
