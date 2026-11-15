import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { ToastProvider } from "@/components/ui";
import { clearSession, saveSession, type Role } from "@/lib/session";

export const ORG = "11111111-1111-4111-8111-111111111111";

export function signIn(role: Role = "DISPATCHER"): void {
  saveSession({
    token: "test-token",
    expiresAt: new Date(Date.now() + 3600_000).toISOString(),
    user: { id: "u1", email: "dispatcher@example.com", full_name: "Test Dispatcher" },
    memberships: [
      {
        membership_id: "m1",
        organization_id: ORG,
        organization_name: "Test Org",
        timezone: "Asia/Bishkek",
        currency: "KGS",
        role,
        technician_id: null,
      },
    ],
    orgId: ORG,
  });
}

export function signOut(): void {
  clearSession();
}

export function renderWithProviders(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}

type Handler = (url: URL, init: RequestInit) => { status?: number; body: unknown; wait?: Promise<void> } | undefined;

/** Install a fake fetch. Handlers are tried in order; the first to answer wins. */
export function mockFetch(...handlers: Handler[]) {
  const calls: { method: string; url: URL; body: unknown }[] = [];
  const fn = jest.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input));
    const method = (init.method ?? "GET").toUpperCase();
    let body: unknown = undefined;
    if (typeof init.body === "string") body = JSON.parse(init.body);
    calls.push({ method, url, body });
    for (const handler of handlers) {
      const answer = handler(url, init);
      if (answer) {
        if (answer.wait) await answer.wait;
        const status = answer.status ?? 200;
        return {
          ok: status < 400,
          status,
          text: async () => JSON.stringify(answer.body),
        } as Response;
      }
    }
    return { ok: false, status: 404, text: async () => JSON.stringify({ error: { code: "NOT_FOUND", message: "no mock" } }) } as Response;
  });
  global.fetch = fn as unknown as typeof fetch;
  return { fn, calls };
}

export const emptyPage = { items: [], total: 0, page: 1, page_size: 15, total_pages: 0 };
