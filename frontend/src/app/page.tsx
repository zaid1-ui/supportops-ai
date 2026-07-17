'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Shell } from '@/components/shell';
import { Empty, ErrorBox, Loading, PageHeader, Stat, Status } from '@/components/ui';

export default function Dashboard() {
  const metrics = useQuery({ queryKey: ['metrics'], queryFn: api.metrics, refetchInterval: 15_000 });
  const approvals = useQuery({ queryKey: ['approvals'], queryFn: api.approvals, refetchInterval: 10_000 });

  return (
    <Shell>
      <PageHeader title="Dashboard" description="What the platform is doing, and what needs you." />

      {metrics.isLoading && <Loading />}
      {metrics.error != null && <ErrorBox error={metrics.error} />}

      {metrics.data && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Waiting on you" value={String(approvals.data?.length ?? 0)} sub="Approvals pending" />
          <Stat label="Runs" value={String(metrics.data.total_runs)} sub="All time" />
          <Stat label="Completion" value={`${Math.round(metrics.data.workflow_completion_rate * 100)}%`} sub="Of finished runs" />
          <Stat label="Failures" value={`${Math.round(metrics.data.failure_rate * 100)}%`} sub="Of finished runs" />
        </div>
      )}

      <section className="mt-6">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-ink">Approval queue</h2>
          <Link href="/approvals" className="text-sm text-signal hover:underline">Open queue</Link>
        </div>

        {approvals.isLoading && <Loading />}
        {approvals.data?.length === 0 && (
          <Empty title="Queue is clear" hint="Start a workflow from Workflows to put a draft in front of a reviewer." />
        )}
        {!!approvals.data?.length && (
          <ul className="card divide-y divide-line">
            {approvals.data.slice(0, 5).map((a) => (
              <li key={a.id} className="flex items-center gap-3 p-3">
                <Status value={a.kind} />
                <span className="min-w-0 flex-1 truncate text-sm text-ink">{a.reason}</span>
                <span className="font-mono text-micro text-faint">{new Date(a.created_at).toLocaleTimeString()}</span>
                <Link href="/approvals" className="btn-ghost">Review</Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {metrics.data && Object.keys(metrics.data.runs_by_status).length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 text-sm font-semibold text-ink">Runs by status</h2>
          <div className="card divide-y divide-line">
            {Object.entries(metrics.data.runs_by_status).map(([k, v]) => (
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
