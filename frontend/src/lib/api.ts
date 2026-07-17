/**
 * Typed client for the SupportOps API.
 *
 * Mirrors backend/app/schemas/api.py. The backend returns one error envelope for
 * every failure (backend/app/core/errors.py), so exactly one function here parses
 * errors and callers switch on `code`, never on the prose in `message`.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const TOKEN_KEY = 'supportops_token';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string) { window.localStorage.setItem(TOKEN_KEY, t); }
export function clearToken() { window.localStorage.removeItem(TOKEN_KEY); }

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');

  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  if (res.status === 401) {
    // Token gone or expired. Drop it and bounce to login rather than letting
    // every subsequent call fail with the same 401.
    clearToken();
    if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
    throw new ApiError(401, 'unauthorized', 'Session expired. Sign in again.');
  }

  if (!res.ok) {
    let code = 'error';
    let message = res.statusText || 'Request failed';
    try {
      const body = await res.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
      const fieldErrors = body?.error?.details?.errors;
      if (Array.isArray(fieldErrors) && fieldErrors.length) {
        message = fieldErrors.map((e: any) => `${e.loc?.slice(1).join('.')}: ${e.msg}`).join('; ');
      }
    } catch { /* non-JSON body; keep statusText */ }
    throw new ApiError(res.status, code, message);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type Role = 'agent' | 'engineer' | 'lead' | 'admin';
export interface User { id: string; email: string; full_name: string; role: Role }
export interface AgentInfo {
  name: string; role: string; goal: string; tier: string;
  tools: string[]; max_iter: number; allow_delegation: boolean;
}
export interface DocumentRec {
  id: string; filename: string; doc_type: string; product_area: string;
  version: string | null; status: string; chunk_count: number;
  error: string | null; created_at: string;
}
export interface SearchHit {
  chunk_id: string; doc_id: string; source: string; page: number | null;
  heading: string | null; score: number; content: string;
}
export interface SearchResponse { query: string; product_area: string | null; hits: SearchHit[]; total: number }
export interface WorkflowEvent {
  event_type: string; agent: string | null; task: string | null; tool: string | null;
  payload: Record<string, any>; duration_ms: number | null; created_at: string;
}
export interface WorkflowStatus {
  run_id: string; workflow: string; status: string; ticket_id: string | null;
  current_task: string | null; error: string | null; state: Record<string, any>;
  events: WorkflowEvent[]; started_at: string; completed_at: string | null;
}
export interface RunResponse { run_id: string; workflow: string; status: string; awaiting_approval_id: string | null }
export interface Approval {
  id: string; run_id: string; kind: string; status: string; reason: string;
  payload: Record<string, any>; decided_by: string | null; decided_at: string | null; created_at: string;
}
export interface Metrics {
  workflow_completion_rate: number; agent_success_rates: Record<string, number>;
  tool_usage: Record<string, number>; failure_rate: number; approval_rate: number;
  total_runs: number; runs_by_status: Record<string, number>;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; expires_in_minutes: number }>('/auth/login', {
      method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => request<User>('/auth/me'),

  agents: () => request<AgentInfo[]>('/agents'),
  executeAgent: (agent: string, task: string) =>
    request<{ agent: string; output: string; duration_ms: number }>('/agents/execute', {
      method: 'POST', body: JSON.stringify({ agent, task, context: {} }) }),

  documents: () => request<DocumentRec[]>('/documents'),
  uploadDocument: (file: File, productArea: string, version?: string) => {
    const fd = new FormData(); fd.append('file', file);
    const q = new URLSearchParams({ product_area: productArea });
    if (version) q.set('version', version);
    return request<DocumentRec>(`/documents/upload?${q}`, { method: 'POST', body: fd });
  },
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
  search: (q: string, productArea?: string, topK = 5) => {
    const p = new URLSearchParams({ q, top_k: String(topK) });
    if (productArea) p.set('product_area', productArea);
    return request<SearchResponse>(`/documents/search?${p}`);
  },

  workflows: () => request<string[]>('/workflows'),
  runWorkflow: (workflow: string, ticketId: string) =>
    request<RunResponse>('/workflows/run', {
      method: 'POST', body: JSON.stringify({ workflow, ticket_id: ticketId }) }),
  workflowStatus: (runId: string) => request<WorkflowStatus>(`/workflows/${runId}/status`),

  approvals: () => request<Approval[]>('/approvals'),
  decide: (id: string, status: 'approved' | 'rejected' | 'edited',
           editedPayload?: Record<string, any>, feedback?: string) =>
    request<Approval>(`/approvals/${id}/decide`, {
      method: 'POST',
      body: JSON.stringify({ status, edited_payload: editedPayload ?? null, feedback: feedback ?? null }) }),

  metrics: () => request<Metrics>('/metrics'),
};

export const PRODUCT_AREAS = ['exports', 'billing', 'authentication', 'integrations', 'reporting', 'api'];
