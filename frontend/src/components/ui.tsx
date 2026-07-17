'use client';

import { AlertCircle, Loader2 } from 'lucide-react';

/** Severity is data, not decoration — these map to the S1..S4 triage rubric. */
export function Severity({ value }: { value?: string | null }) {
  if (!value) return <span className="text-faint">—</span>;
  const tone: Record<string, string> = {
    S1: 'bg-[#FDECEA] text-s1', S2: 'bg-[#FEF3E2] text-s2',
    S3: 'bg-signal-soft text-s3', S4: 'bg-paper text-s4',
  };
  return <span className={`chip ${tone[value] ?? 'bg-paper text-s4'}`}>{value}</span>;
}

export function Status({ value }: { value: string }) {
  const tone: Record<string, string> = {
    completed: 'bg-[#E8F5EE] text-ok', indexed: 'bg-[#E8F5EE] text-ok',
    approved: 'bg-[#E8F5EE] text-ok', running: 'bg-signal-soft text-signal',
    awaiting_approval: 'bg-[#FEF3E2] text-warn', pending: 'bg-[#FEF3E2] text-warn',
    failed: 'bg-[#FDECEA] text-danger', escalated: 'bg-[#FDECEA] text-danger',
    rejected: 'bg-[#FDECEA] text-danger',
  };
  return (
    <span className={`chip ${tone[value] ?? 'bg-paper text-muted'}`}>
      {value.replace(/_/g, ' ')}
    </span>
  );
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-muted">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}…
    </div>
  );
}

/** Errors state what happened and what to do. They do not apologise. */
export function ErrorBox({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : 'Request failed';
  return (
    <div className="card flex items-start gap-2 border-[#F3C9C4] bg-[#FDF6F5] p-3 text-sm">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden />
      <span className="text-ink">{msg}</span>
    </div>
  );
}

/** An empty screen is an invitation to act, not a shrug. */
export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="card p-10 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint && <p className="mt-1 text-sm text-muted">{hint}</p>}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card p-4">
      <p className="eyebrow">{label}</p>
      <p className="mt-1 font-mono text-2xl tracking-tight text-ink">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
    </div>
  );
}

export function PageHeader({ title, description, children }: {
  title: string; description: string; children?: React.ReactNode;
}) {
  return (
    <header className="mb-5 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        <p className="mt-0.5 text-sm text-muted">{description}</p>
      </div>
      {children}
    </header>
  );
}
