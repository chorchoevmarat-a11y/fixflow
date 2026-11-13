import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StatusBadge } from "@/components/badges";
import { RequestActions } from "@/components/request-actions";
import { useApiQuery } from "@/lib/hooks";
import type { RequestDetail } from "@/lib/types";
import { mockFetch, renderWithProviders, signIn } from "./utils";

function detail(status: RequestDetail["status"], actions: string[], extra: Partial<RequestDetail> = {}): RequestDetail {
  return {
    id: "r1",
    reference: "REQ-00001",
    title: "Boiler pressure drops",
    status,
    priority: "HIGH",
    description: "Boiler pressure keeps dropping every morning.",
    allowed_actions: actions,
    assigned_to_me: false,
    start_blocked_reason: null,
    blocker_reason: null,
    triage_notes: null,
    ...extra,
  } as RequestDetail;
}

/** A page-like harness: fetches the request and renders status + actions. */
function Harness() {
  const query = useApiQuery<RequestDetail>("/requests/r1");
  if (!query.data) return <p>loading</p>;
  return (
    <>
      <StatusBadge status={query.data.status} />
      <RequestActions request={query.data} />
    </>
  );
}

describe("backend-driven mutation", () => {
  beforeEach(() => signIn("DISPATCHER"));

  it("triage posts to the API and the screen refreshes from the server without a reload", async () => {
    let triaged = false;
    const { calls } = mockFetch(
      (url, init) => {
        if (url.pathname.endsWith("/requests/r1/triage") && init.method === "POST") {
          triaged = true;
          return { body: detail("TRIAGED", ["assign"]) };
        }
        return undefined;
      },
      (url) =>
        url.pathname.endsWith("/requests/r1")
          ? { body: triaged ? detail("TRIAGED", ["assign"]) : detail("SUBMITTED", ["triage", "cancel"]) }
          : undefined,
    );
    renderWithProviders(<Harness />);

    const button = await screen.findByRole("button", { name: "Mark as triaged" });
    expect(screen.getByText(/Submitted/)).toBeInTheDocument();
    await userEvent.click(button);

    // The status badge flips because the cache was invalidated and re-fetched.
    await waitFor(() => expect(screen.getByText(/Triaged/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Mark as triaged" })).not.toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
    expect(calls.filter((c) => c.method === "GET" && c.url.pathname.endsWith("/requests/r1")).length).toBeGreaterThanOrEqual(2);
  });

  it("surfaces a rejected action as an error and keeps the old state (never fakes success)", async () => {
    mockFetch(
      (url, init) =>
        url.pathname.endsWith("/triage") && init.method === "POST"
          ? { status: 409, body: { error: { code: "INVALID_TRANSITION", message: "Cannot triage a request that is TRIAGED." } } }
          : undefined,
      (url) => (url.pathname.endsWith("/requests/r1") ? { body: detail("SUBMITTED", ["triage"]) } : undefined),
    );
    renderWithProviders(<Harness />);
    await userEvent.click(await screen.findByRole("button", { name: "Mark as triaged" }));
    expect(await screen.findByText(/Cannot triage a request/)).toBeInTheDocument();
    expect(screen.getByText(/Submitted/)).toBeInTheDocument();
  });

  it("disables double submission while a mutation is pending", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    const { calls } = mockFetch((url, init) => {
      if (url.pathname.endsWith("/triage") && init.method === "POST") {
        return { body: detail("TRIAGED", ["assign"]), wait: gate };
      }
      return url.pathname.endsWith("/requests/r1") ? { body: detail("SUBMITTED", ["triage"]) } : undefined;
    });
    renderWithProviders(<Harness />);
    const button = await screen.findByRole("button", { name: "Mark as triaged" });
    await userEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    await userEvent.click(button);
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
    release();
  });
});
