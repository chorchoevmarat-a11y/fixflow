import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RequestList } from "@/components/request-list";
import type { RequestRow } from "@/lib/types";
import { mockFetch, renderWithProviders, signIn } from "./utils";

function row(id: string, reference: string, title: string, status: RequestRow["status"], priority: RequestRow["priority"]): RequestRow {
  return {
    id,
    reference,
    title,
    status,
    priority,
    created_at: "2026-11-10T05:00:00Z",
    updated_at: "2026-11-10T05:00:00Z",
    completed_at: null,
    requester_name: "Cholpon",
    property: { id: "p1", name: "Main Academic Building", address: "Salymbekov University main campus" },
    category: { id: "c1", name: "HVAC" },
    asset_id: null,
    assignment: null,
    is_preventive: false,
    sla: {
      state: "ON_TRACK",
      budget_seconds: 28800,
      consumed_seconds: 0,
      remaining_seconds: 28800,
      due_at: "2026-11-11T05:00:00Z",
      paused: false,
      stopped_at: null,
      escalated_at: null,
    },
  };
}

const ALL = [row("1", "REQ-00001", "Boiler pressure drops", "TRIAGED", "HIGH"), row("2", "REQ-00002", "Door lock jammed", "SUBMITTED", "LOW")];

function server() {
  return mockFetch(
    (url) => (url.pathname.endsWith("/categories") || url.pathname.endsWith("/technicians") ? { body: [] } : undefined),
    (url) => {
      if (!url.pathname.endsWith("/requests")) return undefined;
      const q = url.searchParams.get("q")?.toLowerCase() ?? "";
      const priority = url.searchParams.get("priority");
      const items = ALL.filter((r) => (!q || r.title.toLowerCase().includes(q)) && (!priority || r.priority === priority));
      return { body: { items, total: items.length, page: 1, page_size: 15, total_pages: 1 } };
    },
  );
}

describe("request list search and filters", () => {
  beforeEach(() => signIn("DISPATCHER"));

  it("loads the queue and renders every row with status and priority labels", async () => {
    server();
    renderWithProviders(<RequestList />);
    expect((await screen.findAllByText("Boiler pressure drops")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Door lock jammed").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/High/).length).toBeGreaterThan(0); // text, not only color
  });

  it("sends the search term to the server and shows the filtered result", async () => {
    const { calls } = server();
    renderWithProviders(<RequestList />);
    await screen.findAllByText("Door lock jammed");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search" }), "boiler");
    // Wait for the filtered response to render, then confirm the other row is gone.
    await waitFor(() => {
      expect(screen.getAllByText("Boiler pressure drops").length).toBeGreaterThan(0);
      expect(screen.queryAllByText("Door lock jammed")).toHaveLength(0);
    });
    const last = calls.filter((c) => c.url.pathname.endsWith("/requests")).at(-1);
    expect(last?.url.searchParams.get("q")).toBe("boiler");
    expect(last?.url.searchParams.get("page")).toBe("1");
  });

  it("applies the priority filter server-side and shows an empty state when nothing matches", async () => {
    const { calls } = server();
    renderWithProviders(<RequestList />);
    await screen.findAllByText("Boiler pressure drops");
    await userEvent.selectOptions(screen.getByLabelText("Priority"), "NORMAL");
    expect(await screen.findByText("No reports match")).toBeInTheDocument();
    const last = calls.filter((c) => c.url.pathname.endsWith("/requests")).at(-1);
    expect(last?.url.searchParams.get("priority")).toBe("NORMAL");
  });
});
