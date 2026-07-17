'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  Activity, BarChart3, FileText, Gauge, Inbox, LogOut, MessageSquare, Search, Workflow,
} from 'lucide-react';
import { api, clearToken, getToken } from '@/lib/api';
import { useEffect, useState } from 'react';

const NAV = [
  { href: '/', label: 'Dashboard', icon: Gauge },
  { href: '/approvals', label: 'Approvals', icon: Inbox },
  { href: '/workflows', label: 'Workflows', icon: Workflow },
  { href: '/agents', label: 'Agents', icon: Activity },
  { href: '/documents', label: 'Documents', icon: FileText },
  { href: '/search', label: 'Knowledge', icon: Search },
  { href: '/chat', label: 'Chat', icon: MessageSquare },
  { href: '/analytics', label: 'Analytics', icon: BarChart3 },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) router.replace('/login');
    else setReady(true);
  }, [router]);

  const { data: user } = useQuery({ queryKey: ['me'], queryFn: api.me, enabled: ready });

  // Approvals are the queue this console exists to clear, so the count is in
  // the nav permanently rather than behind a click.
  const { data: approvals } = useQuery({
    queryKey: ['approvals'], queryFn: api.approvals, enabled: ready, refetchInterval: 10_000,
  });

  if (!ready) return null;

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 border-r border-line bg-surface md:flex md:flex-col">
        <div className="border-b border-line px-4 py-4">
          <p className="text-sm font-semibold tracking-tight">SupportOps</p>
          <p className="eyebrow mt-0.5">Operations console</p>
        </div>

        <nav className="flex-1 p-2">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === '/' ? pathname === '/' : pathname.startsWith(href);
            const pending = href === '/approvals' ? approvals?.length ?? 0 : 0;
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? 'page' : undefined}
                className={`mb-0.5 flex items-center gap-2.5 rounded-card px-2.5 py-2 text-sm transition-colors
                  ${active ? 'bg-signal-soft font-medium text-signal' : 'text-muted hover:bg-paper hover:text-ink'}`}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {label}
                {pending > 0 && (
                  <span className="ml-auto chip bg-[#FEF3E2] text-warn">{pending}</span>
                )}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-line p-3">
          {user && (
            <div className="mb-2 px-1">
              <p className="truncate text-sm text-ink">{user.full_name}</p>
              <p className="eyebrow">{user.role}</p>
            </div>
          )}
          <button
            onClick={() => { clearToken(); router.replace('/login'); }}
            className="btn-ghost w-full justify-center text-muted"
          >
            <LogOut className="h-3.5 w-3.5" aria-hidden /> Sign out
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1 p-5 md:p-7">{children}</main>
    </div>
  );
}
