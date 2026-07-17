'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { api, setToken } from '@/lib/api';
import { ErrorBox } from '@/components/ui';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('lead@example.com');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const { access_token } = await api.login(email, password);
      setToken(access_token);
      router.replace('/');
    } catch (err) { setError(err); } finally { setBusy(false); }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-6">
          <p className="text-lg font-semibold tracking-tight">SupportOps</p>
          <p className="eyebrow mt-0.5">Operations console</p>
        </div>

        <form onSubmit={submit} className="card space-y-3 p-5">
          <div>
            <label htmlFor="email" className="eyebrow mb-1 block">Email</label>
            <input id="email" type="email" required value={email}
                   onChange={(e) => setEmail(e.target.value)} className="input" />
          </div>
          <div>
            <label htmlFor="password" className="eyebrow mb-1 block">Password</label>
            <input id="password" type="password" required value={password}
                   onChange={(e) => setPassword(e.target.value)} className="input" />
          </div>
          {error != null && <ErrorBox error={error} />}
          <button type="submit" disabled={busy} className="btn-primary w-full justify-center">
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="mt-3 text-xs text-muted">
          Seeded by <code className="font-mono">python -m scripts.seed</code>. Roles: agent,
          engineer, lead, admin — password is the role plus 123.
        </p>
      </div>
    </div>
  );
}
