'use client';

import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Shell } from '@/components/shell';
import { ErrorBox, Loading, PageHeader } from '@/components/ui';

export default function AgentsPage() {
  const agents = useQuery({ queryKey: ['agents'], queryFn: api.agents });
  const metrics = useQuery({ queryKey: ['metrics'], queryFn: api.metrics, refetchInterval: 15_000 });

  return (
    <Shell>
      <PageHeader title="Agents" description="The crew, what each one may do, and how often it succeeds." />

      {agents.isLoading && <Loading />}
      {agents.error != null && <ErrorBox error={agents.error} />}

      <div className="grid gap-3 lg:grid-cols-2">
        {agents.data?.map((a) => {
          const rate = metrics.data?.agent_success_rates?.[a.name];
          return (
            <article key={a.name} className="card p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-ink">{a.role}</h2>
                  <p className="eyebrow mt-0.5">{a.name}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {/* Tier is cost. Surfaced because it explains the latency and
                      the bill, and reviewers ask about both. */}
                  <span className={`chip ${a.tier === 'fast' ? 'bg-paper text-muted' : 'bg-signal-soft text-signal'}`}>
                    {a.tier}
                  </span>
                  {rate != null && (
                    <span className="chip bg-[#E8F5EE] text-ok">{Math.round(rate * 100)}%</span>
                  )}
                </div>
              </div>

              <p className="mt-2 text-sm leading-relaxed text-muted">{a.goal}</p>

              <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-micro">
                <dt className="eyebrow">Tools</dt>
                <dd className="flex flex-wrap gap-1">
                  {a.tools.length === 0
                    ? <span className="text-faint">none</span>
                    : a.tools.map((t) => <span key={t} className="chip bg-paper text-muted">{t}</span>)}
                </dd>
                <dt className="eyebrow">Max iter</dt>
                <dd className="font-mono text-muted">{a.max_iter}</dd>
                <dt className="eyebrow">Delegates</dt>
                <dd className="font-mono text-muted">{a.allow_delegation ? 'yes' : 'no'}</dd>
              </dl>
            </article>
          );
        })}
      </div>
    </Shell>
  );
}
