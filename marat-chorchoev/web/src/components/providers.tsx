"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ToastProvider } from "@/components/ui";
import { useSession } from "@/lib/session";

function CacheIsolation({ client }: { client: QueryClient }) {
  // Switching organization or signing out discards every cached response (AUTH-03, WEB-07).
  const session = useSession();
  const scope = session ? `${session.user.id}:${session.orgId ?? ""}` : "";
  const previous = useRef(scope);
  useEffect(() => {
    if (previous.current !== scope) {
      client.clear();
      previous.current = scope;
    }
  }, [client, scope]);
  return null;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 5_000, gcTime: 60_000, refetchOnWindowFocus: true },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <CacheIsolation client={client} />
        {children}
      </ToastProvider>
    </QueryClientProvider>
  );
}
