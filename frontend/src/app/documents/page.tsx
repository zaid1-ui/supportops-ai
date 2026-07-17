'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { useRef, useState } from 'react';
import { api, PRODUCT_AREAS } from '@/lib/api';
import { Shell } from '@/components/shell';
import { Empty, ErrorBox, Loading, PageHeader, Status } from '@/components/ui';

export default function DocumentsPage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [area, setArea] = useState('exports');

  const docs = useQuery({ queryKey: ['documents'], queryFn: api.documents });

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDocument(file, area),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['documents'] });
      if (fileRef.current) fileRef.current.value = '';
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteDocument(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });

  return (
    <Shell>
      <PageHeader title="Documents" description="The knowledge agents are allowed to cite." />

      <div className="card mb-4 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[180px]">
            <label htmlFor="area" className="eyebrow mb-1 block">Product area</label>
            <select id="area" value={area} onChange={(e) => setArea(e.target.value)} className="input">
              {PRODUCT_AREAS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div className="min-w-[220px] flex-1">
            <label htmlFor="file" className="eyebrow mb-1 block">File</label>
            <input
              id="file" ref={fileRef} type="file" accept=".pdf,.docx,.txt"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); }}
              className="input file:mr-3 file:rounded file:border-0 file:bg-paper file:px-2 file:py-1 file:text-sm"
            />
          </div>
        </div>
        <p className="mt-2 text-xs text-muted">
          PDF, DOCX, or TXT. Product area scopes retrieval — a wrong value hides the document from
          the agents that need it. Ingestion runs on upload and may take a moment.
        </p>
        {upload.isPending && <Loading label="Chunking and embedding" />}
        {upload.error != null && <div className="mt-3"><ErrorBox error={upload.error} /></div>}
      </div>

      {docs.isLoading && <Loading />}
      {docs.error != null && <ErrorBox error={docs.error} />}
      {docs.data?.length === 0 && (
        <Empty title="No documents yet" hint="Upload a runbook or KB article and agents can start citing it." />
      )}

      {!!docs.data?.length && (
        <div className="card divide-y divide-line">
          {docs.data.map((d) => (
            <div key={d.id} className="flex items-center gap-3 p-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-ink">{d.filename}</p>
                <p className="mt-0.5 font-mono text-micro text-faint">
                  {d.product_area} · {d.doc_type} · {d.chunk_count} chunks
                  {d.version ? ` · ${d.version}` : ''}
                </p>
                {d.error && <p className="mt-0.5 text-xs text-danger">{d.error}</p>}
              </div>
              <Status value={d.status} />
              <button
                onClick={() => remove.mutate(d.id)}
                aria-label={`Delete ${d.filename}`}
                className="btn-ghost text-muted hover:text-danger"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden />
              </button>
            </div>
          ))}
        </div>
      )}
    </Shell>
  );
}
