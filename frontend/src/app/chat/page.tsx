'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '@/lib/api';
import { Shell } from '@/components/shell';
import { ErrorBox, Loading, PageHeader } from '@/components/ui';

interface Turn { agent: string; task: string; output: string; ms: number }

/**
 * Chat workspace.
 *
 * Deliberately not a general chatbot: you pick which specialist answers. That
 * constraint is the platform's whole thesis made visible — asking the Validation
 * Agent to draft a reply should feel wrong, and here it looks wrong too.
 *
 * This is a debugging surface. Nothing here can reach a customer: /agents/execute
 * has no workflow, no state, and no send path.
 */
export default function ChatPage() {
  const [agent, setAgent] = useState('research');
  const [task, setTask] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);

  const agents = useQuery({ queryKey: ['agents'], queryFn: api.agents });

  const send = useMutation({
    mutationFn: () => api.executeAgent(agent, task),
    onSuccess: (r) => {
      setTurns((t) => [...t, { agent: r.agent, task, output: r.output, ms: r.duration_ms }]);
      setTask('');
    },
  });

  const selected = agents.data?.find((a) => a.name === agent);

  return (
    <Shell>
      <PageHeader title="Chat" description="Ask one specialist directly. For debugging, not for customers." />

      <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
        <div className="card h-fit p-3">
          <label htmlFor="ag" className="eyebrow mb-1 block">Agent</label>
          <select id="ag" value={agent} onChange={(e) => setAgent(e.target.value)} className="input">
            {agents.data?.map((a) => <option key={a.name} value={a.name}>{a.name}</option>)}
          </select>
          {selected && (
            <>
              <p className="mt-3 text-xs leading-relaxed text-muted">{selected.goal}</p>
              <div className="mt-3 flex flex-wrap gap-1">
                {selected.tools.map((t) => <span key={t} className="chip bg-paper text-muted">{t}</span>)}
              </div>
            </>
          )}
        </div>

        <div className="space-y-3">
          {turns.length === 0 && (
            <div className="card p-8 text-center">
              <p className="text-sm font-medium text-ink">Pick an agent and ask it something</p>
              <p className="mt-1 text-sm text-muted">
                Each agent only does its own job — the Research Agent retrieves, it does not advise.
              </p>
            </div>
          )}

          {turns.map((t, i) => (
            <div key={i} className="space-y-2">
              <div className="card bg-paper p-3">
                <p className="eyebrow">You → {t.agent}</p>
                <p className="mt-1 text-sm text-ink">{t.task}</p>
              </div>
              <div className="card p-3">
                <div className="flex items-baseline gap-2">
                  <p className="eyebrow">{t.agent}</p>
                  <span className="ml-auto font-mono text-micro text-faint">{Math.round(t.ms)}ms</span>
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-ink">{t.output}</p>
              </div>
            </div>
          ))}

          {send.isPending && <Loading label={`${agent} is working`} />}
          {send.error != null && <ErrorBox error={send.error} />}

          <form
            onSubmit={(e) => { e.preventDefault(); if (task.trim()) send.mutate(); }}
            className="card flex items-end gap-2 p-3"
          >
            <div className="flex-1">
              <label htmlFor="task" className="sr-only">Task</label>
              <textarea
                id="task" value={task} onChange={(e) => setTask(e.target.value)} rows={2}
                placeholder="Search the knowledge base for CSV export timeout behaviour"
                className="input resize-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && task.trim()) send.mutate();
                }}
              />
            </div>
            <button type="submit" disabled={!task.trim() || send.isPending} className="btn-primary">
              Send
            </button>
          </form>
        </div>
      </div>
    </Shell>
  );
}
