'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '@/lib/api';
import { Shell } from '@/components/shell';
import { Trace } from '@/components/trace';
import { Empty, ErrorBox, Loading, PageHeader, Status } from '@/components/ui';

export default function WorkflowsPage() {
  const qc = useQueryClient();
  const [ticketId, setTicketId] = useState('TK-1001');
  const [runId, setRunId] = useState<string | null>(null);

  const workflows = useQuery({ queryKey: ['workflows'], queryFn: api.workflows });
  const [workflow, setWorkflow] = useState('ticket_resolution');

  const status = useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.workflowStatus(runId!),
    enabled: !!runId,
    // Poll while in flight; stop once the run is terminal or parked on a human.
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s && ['completed', 'failed', 'escalated', 'awaiting_approval'].includes(s) ? false : 3_000;
    },
  });

  const start = useMutation({
    mutationFn: () => api.runWorkflow(workflow, ticketId),
    onSuccess: (r) => {
      setRunId(r.run_id);
      qc.invalidateQueries({ queryKey: ['approvals'] });
      qc.invalidateQueries({ queryKey: ['metrics'] });
    },
  });

  return (
    <Shell>
      <PageHeader title="Workflows" description="Start a run and watch the crew work." />

      <div className="card mb-4 flex flex-wrap items-end gap-3 p-4">
        <div className="min-w-[200px]">
          <label htmlFor="wf" className="eyebrow mb-1 block">Workflow</label>
          <select id="wf" value={workflow} onChange={(e) => setWorkflow(e.target.value)} className="input">
            {workflows.data?.map((w) => <option key={w} value={w}>{w.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <div className="min-w-[160px]">
          <label htmlFor="tk" className="eyebrow mb-1 block">Ticket</label>
          <input id="tk" value={ticketId} onChange={(e) => setTicketId(e.target.value)} className="input font-mono" />
        </div>
        <button onClick={() => start.mutate()} disabled={start.isPending} className="btn-primary">
          {start.isPending ? 'Starting…' : 'Start run'}
        </button>
        <p className="text-xs text-muted">
          Seeded tickets: TK-1001, TK-1002, TK-1003. A run takes minutes and stops at an approval gate.
        </p>
      </div>

      {start.error != null && <ErrorBox error={start.error} />}
      {!runId && <Empty title="No run selected" hint="Start a run above to see its trace here." />}

      {runId && (
        <div className="space-y-4">
          <div className="card flex flex-wrap items-center gap-3 p-4">
            <Status value={status.data?.status ?? 'pending'} />
            <span className="font-mono text-micro text-faint">run {runId.slice(0, 8)}</span>
            {status.data?.current_task && (
              <span className="chip bg-signal-soft text-signal">{status.data.current_task}</span>
            )}
            {status.data?.status === 'awaiting_approval' && (
              <a href="/approvals" className="btn-primary ml-auto">Review in Approvals</a>
            )}
          </div>

          {status.data?.error && <ErrorBox error={new Error(status.data.error)} />}

          <div className="card">
            <div className="border-b border-line px-4 py-2.5">
              <p className="eyebrow">Trace</p>
            </div>
            {status.isLoading ? <Loading label="Loading trace" /> : <Trace events={status.data?.events ?? []} />}
          </div>
        </div>
      )}
    </Shell>
  );
}
