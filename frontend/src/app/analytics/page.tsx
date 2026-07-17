'use client';

import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Shell } from '@/components/shell';
import { Empty, ErrorBox, Loading, PageHeader, Stat, Status } from '@/components/ui';

/** Bar rendered from the data, not a chart library. One dependency saved. */
function Bar({ label, value, max, format }: {
  label: string; value: number; max: number; format?: (n: number) => string;
}) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="w-32 shrink-0 truncate text-sm text-muted">{label}</span>
      <div className="h-4 flex-1 overflow-hidden rounded-sm bg-paper">
        <div className="h-full bg-signal" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-14 shrink-0 text-right font-mono text-micro text-ink">
        {format ? format(value) : value}
      </span>
    </div>
  );
}

export default function AnalyticsPage() {
  const m = useQuery({ queryKey: ['metrics'], queryFn: api.metrics, refetchInterval: 15_000 });

  if (m.isLoading) return <Shell><Loading /></Shell>;
  if (m.error != null) return <Shell><ErrorBox error={m.error} /></Shell>;
  if (!m.data) return null;

  const successes = Object.entries(m.data.agent_success_rates);
  const tools = Object.entries(m.data.tool_usage);
  const maxTool = Math.max(1, ...tools.map(([, v]) => v));

  return (
    <Shell>
      <PageHeader title="Analytics" description="Every figure comes from the run event trace." />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Runs" value={String(m.data.total_runs)} sub="All time" />
        <Stat label="Completion" value={`${Math.round(m.data.workflow_completion_rate * 100)}%`} sub="Of finished runs" />
        <Stat label="Failure" value={`${Math.round(m.data.failure_rate * 100)}%`} sub="Of finished runs" />
        <Stat label="Approval" value={`${Math.round(m.data.approval_rate * 100)}%`} sub="Drafts humans accepted" />
      </div>

      {m.data.total_runs === 0 && (
        <div className="mt-4">
          <Empty title="No runs yet" hint="Start a workflow and these fill in from its events." />
        </div>
      )}

      {successes.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-1 text-sm font-semibold text-ink">Agent success rate</h2>
          <p className="mb-2 text-xs text-muted">Completed tasks over attempted, per agent.</p>
          <div className="card p-4">
            {successes.map(([name, rate]) => (
              <Bar key={name} label={name} value={rate} max={1} format={(n) => `${Math.round(n * 100)}%`} />
            ))}
          </div>
        </section>
      )}

      {tools.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-1 text-sm font-semibold text-ink">Tool usage</h2>
          <p className="mb-2 text-xs text-muted">Calls counted before execution, so hung calls still appear.</p>
          <div className="card p-4">
            {tools.map(([name, count]) => <Bar key={name} label={name} value={count} max={maxTool} />)}
          </div>
        </section>
      )}

      {Object.keys(m.data.runs_by_status).length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 text-sm font-semibold text-ink">Runs by status</h2>
          <div className="card divide-y divide-line">
            {Object.entries(m.data.runs_by_status).map(([k, v]) => (
              <div key={k} className="flex items-center gap-3 p-2.5">
                <Status value={k} />
                <span className="ml-auto font-mono text-sm text-ink">{v}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </Shell>
  );
}
