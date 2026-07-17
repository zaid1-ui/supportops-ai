'use client';

import type { WorkflowEvent } from '@/lib/api';

/**
 * The agent trace.
 *
 * This is the element that distinguishes the platform from a chatbot: it shows
 * the chain of specialists that produced a draft, what each one did, which tools
 * it called, and where a gate opened. A reviewer approving a customer-facing
 * message is entitled to see how it was arrived at, and the events table already
 * records exactly that — this just renders it.
 */

const TONE: Record<string, string> = {
  task_completed: 'border-ok bg-[#E8F5EE]',
  task_failed: 'border-danger bg-[#FDECEA]',
  validation_failed: 'border-warn bg-[#FEF3E2]',
  approval_requested: 'border-warn bg-[#FEF3E2]',
  approval_decided: 'border-signal bg-signal-soft',
  degraded: 'border-warn bg-[#FEF3E2]',
  tool_failed: 'border-danger bg-[#FDECEA]',
  run_completed: 'border-ok bg-[#E8F5EE]',
  run_failed: 'border-danger bg-[#FDECEA]',
};

export function Trace({ events }: { events: WorkflowEvent[] }) {
  if (!events.length) {
    return <p className="p-4 text-sm text-muted">No events recorded yet.</p>;
  }
  return (
    <ol className="relative space-y-0 pl-4">
      {/* One continuous rule: the run is a sequence, and the line says so. */}
      <span aria-hidden className="absolute left-[5px] top-2 bottom-2 w-px bg-line" />
      {events.map((e, i) => (
        <li key={i} className="relative py-2 pl-4">
          <span
            aria-hidden
            className={`absolute -left-[0.05rem] top-3.5 h-2.5 w-2.5 rounded-full border-2 bg-surface
              ${TONE[e.event_type] ?? 'border-line'}`}
          />
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="font-mono text-micro text-ink">{e.event_type.replace(/_/g, ' ')}</span>
            {e.agent && <span className="chip bg-paper text-muted">{e.agent}</span>}
            {e.tool && <span className="chip bg-signal-soft text-signal">{e.tool}</span>}
            {e.duration_ms != null && (
              <span className="font-mono text-micro text-faint">{Math.round(e.duration_ms)}ms</span>
            )}
            <span className="ml-auto font-mono text-micro text-faint">
              {new Date(e.created_at).toLocaleTimeString()}
            </span>
          </div>
          {Object.keys(e.payload ?? {}).length > 0 && (
            <pre className="mt-1 overflow-x-auto rounded border border-line bg-paper p-2 font-mono text-micro text-muted">
              {JSON.stringify(e.payload, null, 2)}
            </pre>
          )}
        </li>
      ))}
    </ol>
  );
}

/** Citations are the grounding claim made checkable. Render them as evidence. */
export function Citations({ citations }: { citations: any[] }) {
  if (!citations?.length) {
    return <p className="text-sm text-warn">No citations. Every factual claim should carry one.</p>;
  }
  return (
    <ul className="space-y-1">
      {citations.map((c, i) => (
        <li key={i} className="flex flex-wrap items-baseline gap-2 font-mono text-micro">
          <span className="chip bg-paper text-muted">#{String(c.chunk_id).slice(0, 8)}</span>
          <span className="text-ink">{c.source}</span>
          {c.page && <span className="text-faint">p{c.page}</span>}
          {c.score != null && <span className="ml-auto text-faint">{Number(c.score).toFixed(3)}</span>}
        </li>
      ))}
    </ul>
  );
}
