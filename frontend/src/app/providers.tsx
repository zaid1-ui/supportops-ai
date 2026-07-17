'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        // A run in flight changes second to second; a stale queue is worse than
        // a refetch. Approvals and runs override this with their own interval.
        staleTime: 5_000,
        retry: (count, err: any) => (err?.status === 401 || err?.status === 403 ? false : count < 2),
      },
    },
  }));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
