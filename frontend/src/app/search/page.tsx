'use client';

import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { api, PRODUCT_AREAS, type SearchResponse } from '@/lib/api';
import { Shell } from '@/components/shell';
import { Empty, ErrorBox, Loading, PageHeader } from '@/components/ui';

export default function SearchPage() {
  const [q, setQ] = useState('');
  const [area, setArea] = useState('');

  const search = useMutation<SearchResponse>({
    mutationFn: () => api.search(q, area || undefined, 8),
  });

  return (
    <Shell>
      <PageHeader title="Knowledge" description="Search exactly what the agents search." />

      <form
        onSubmit={(e) => { e.preventDefault(); if (q.trim()) search.mutate(); }}
        className="card mb-4 flex flex-wrap items-end gap-3 p-4"
      >
        <div className="min-w-[240px] flex-1">
          <label htmlFor="q" className="eyebrow mb-1 block">Query</label>
          <input id="q" value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="why does a large csv export fail" className="input" />
        </div>
        <div className="min-w-[160px]">
          <label htmlFor="pa" className="eyebrow mb-1 block">Scope</label>
          <select id="pa" value={area} onChange={(e) => setArea(e.target.value)} className="input">
            <option value="">All areas</option>
            {PRODUCT_AREAS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <button type="submit" disabled={!q.trim() || search.isPending} className="btn-primary">
          Search
        </button>
      </form>

      {search.isPending && <Loading label="Searching" />}
      {search.error != null && <ErrorBox error={search.error} />}

      {search.data?.total === 0 && (
        <Empty
          title="No results"
          hint="Try the product's own wording rather than the customer's — that mismatch is the usual cause of a false knowledge gap."
        />
      )}

      {!!search.data?.hits.length && (
        <>
          <p className="mb-2 text-sm text-muted">
            {search.data.total} chunk{search.data.total === 1 ? '' : 's'}
            {search.data.product_area ? ` in ${search.data.product_area}` : ' across all areas'}
          </p>
          <div className="space-y-3">
            {search.data.hits.map((h) => (
              <article key={h.chunk_id} className="card p-4">
                {/* Provenance sits with the text, the same way it reaches the agent. */}
                <div className="mb-2 flex flex-wrap items-baseline gap-2 font-mono text-micro">
                  <span className="chip bg-paper text-muted">#{h.chunk_id.slice(0, 8)}</span>
                  <span className="text-ink">{h.source}</span>
                  {h.page && <span className="text-faint">p{h.page}</span>}
                  {h.heading && <span className="text-faint">— {h.heading}</span>}
                  <span className="ml-auto text-signal">{h.score.toFixed(3)}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted">{h.content}</p>
              </article>
            ))}
          </div>
        </>
      )}
    </Shell>
  );
}
