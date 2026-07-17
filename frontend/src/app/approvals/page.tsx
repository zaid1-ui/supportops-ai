'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api, type Approval } from '@/lib/api';
import { Shell } from '@/components/shell';
import { Citations, Trace } from '@/components/trace';
import { Empty, ErrorBox, Loading, PageHeader, Severity, Status } from '@/components/ui';

/**
 * The human-in-the-loop surface (Part 9).
 *
 * A reviewer needs three things before deciding: what the customer asked, what
 * the platform wants to send, and how it got there. The trace is shown beside
 * the draft rather than behind a tab, because a draft with hidden provenance is
 * exactly the thing this platform exists not to produce.
 */
export default function ApprovalsPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Approval | null>(null);
  const [draft, setDraft] = useState('');
  const [feedback, setFeedback] = useState('');

  const inbox = useQuery({ queryKey: ['approvals'], queryFn: api.approvals, refetchInterval: 10_000 });
  const run = useQuery({
    queryKey: ['run', selected?.run_id],
    queryFn: () => api.workflowStatus(selected!.run_id),
    enabled: !!selected,
  });

  const decide = useMutation({
    mutationFn: ({ status }: { status: 'approved' | 'rejected' | 'edited' }) => {
      const edited = status === 'edited' ? { draft_response: draft } : undefined;
      return api.decide(selected!.id, status, edited, feedback || undefined);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approvals'] });
      qc.invalidateQueries({ queryKey: ['metrics'] });
      setSelected(null); setDraft(''); setFeedback('');
    },
  });

  function open(a: Approval) {
    setSelected(a);
    setDraft(a.payload?.draft_response ?? '');
    setFeedback('');
  }

  const edited = !!selected?.payload?.draft_response && draft !== selected.payload.draft_response;

  return (
    <Shell>
      <PageHeader title="Approvals" description="Nothing reaches a customer until you approve it." />

      {inbox.isLoading && <Loading />}
      {inbox.error != null && <ErrorBox error={inbox.error} />}
      {inbox.data?.length === 0 && (
        <Empty title="Queue is clear" hint="Runs that pause for a human land here, oldest first." />
      )}

      {!!inbox.data?.length && (
        <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
          {/* Oldest first — newest-first starves the tickets closest to breaching. */}
          <ul className="card h-fit divide-y divide-line">
            {inbox.data.map((a) => (
              <li key={a.id}>
                <button
                  onClick={() => open(a)}
                  className={`w-full p-3 text-left transition-colors hover:bg-paper
                    ${selected?.id === a.id ? 'bg-signal-soft' : ''}`}
                >
                  <div className="flex items-center gap-2">
                    <Status value={a.kind} />
                    <span className="ml-auto font-mono text-micro text-faint">
                      {new Date(a.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm text-ink">{a.reason}</p>
                  <p className="mt-0.5 font-mono text-micro text-faint">run {a.run_id.slice(0, 8)}</p>
                </button>
              </li>
            ))}
          </ul>

          {!selected && <Empty title="Select an approval" hint="Pick one from the queue to review it." />}

          {selected && (
            <div className="space-y-4">
              <div className="card p-4">
                <p className="eyebrow">Why this stopped</p>
                <p className="mt-1 text-sm text-ink">{selected.reason}</p>
              </div>

              {selected.payload?.escalation && (
                <div className="card p-4">
                  <p className="eyebrow mb-2">Escalation risk</p>
                  <div className="flex items-center gap-2">
                    <Status value={selected.payload.escalation.risk_level} />
                    <span className="font-mono text-sm">
                      {Number(selected.payload.escalation.risk_score).toFixed(2)}
                    </span>
                  </div>
                  <ul className="mt-2 space-y-0.5">
                    {(selected.payload.escalation.drivers ?? []).map((d: string, i: number) => (
                      <li key={i} className="text-sm text-muted">• {d}</li>
                    ))}
                  </ul>
                </div>
              )}

              {selected.payload?.severity && (
                <div className="card flex items-center gap-3 p-4">
                  <p className="eyebrow">Classification</p>
                  <Severity value={selected.payload.severity} />
                  <span className="chip bg-paper text-muted">{selected.payload.product_area}</span>
                  <span className="chip bg-paper text-muted">{selected.payload.queue}</span>
                </div>
              )}

              {selected.payload?.draft_response != null && (
                <div className="card p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="eyebrow">Draft to customer</p>
                    {edited && <span className="chip bg-[#FEF3E2] text-warn">edited</span>}
                  </div>
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    rows={9}
                    className="input font-mono text-xs leading-relaxed"
                    aria-label="Draft response"
                  />
                  {selected.payload.internal_note && (
                    <div className="mt-3 rounded border border-line bg-paper p-2.5">
                      <p className="eyebrow">Internal note — not sent</p>
                      <p className="mt-0.5 text-sm text-muted">{selected.payload.internal_note}</p>
                    </div>
                  )}
                  <div className="mt-3">
                    <p className="eyebrow mb-1">Citations</p>
                    <Citations citations={selected.payload.citations ?? []} />
                  </div>
                </div>
              )}

              <div className="card p-4">
                <label htmlFor="fb" className="eyebrow mb-1 block">Feedback (optional)</label>
                <input id="fb" value={feedback} onChange={(e) => setFeedback(e.target.value)}
                       placeholder="Why you decided this way" className="input" />
                <p className="mt-1 text-xs text-faint">
                  Captured on every decision, not just rejections — approvals are the positive
                  signal the evaluation harness needs.
                </p>
              </div>

              {decide.error != null && <ErrorBox error={decide.error} />}

              <div className="flex gap-2">
                <button
                  onClick={() => decide.mutate({ status: edited ? 'edited' : 'approved' })}
                  disabled={decide.isPending}
                  className="btn-primary"
                >
                  {edited ? 'Approve with edits' : 'Approve'}
                </button>
                <button onClick={() => decide.mutate({ status: 'rejected' })}
                        disabled={decide.isPending} className="btn-danger">
                  Reject
                </button>
                <span className="self-center text-xs text-muted">
                  Rejecting ends the run and hands the ticket to you.
                </span>
              </div>

              <div className="card">
                <div className="border-b border-line px-4 py-2.5">
                  <p className="eyebrow">Agent trace</p>
                  <p className="mt-0.5 text-xs text-muted">
                    How this draft was produced — every agent, tool call, and retry.
                  </p>
                </div>
                {run.isLoading ? <Loading label="Loading trace" /> : <Trace events={run.data?.events ?? []} />}
              </div>
            </div>
          )}
        </div>
      )}
    </Shell>
  );
}
