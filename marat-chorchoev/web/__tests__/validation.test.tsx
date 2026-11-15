import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RequestForm } from "@/components/request-form";
import { validateRequestForm } from "@/lib/validation";
import { emptyPage, mockFetch, renderWithProviders, signIn } from "./utils";

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn(), replace: jest.fn() }) }));

const valid = {
  title: "Air handler is noisy",
  description: "The rooftop unit rattles loudly whenever the fan starts.",
  category_id: "c1",
  property_id: "p1",
  priority: "NORMAL",
};

describe("request validation rules", () => {
  it("accepts a complete request", () => {
    expect(validateRequestForm(valid)).toEqual({});
  });

  it("enforces the 5-120 title and 20-3000 description limits", () => {
    expect(validateRequestForm({ ...valid, title: "Hey" }).title).toMatch(/at least 5/);
    expect(validateRequestForm({ ...valid, title: "x".repeat(121) }).title).toMatch(/at most 120/);
    expect(validateRequestForm({ ...valid, description: "too short" }).description).toMatch(/at least 20/);
    expect(validateRequestForm({ ...valid, description: "y".repeat(3001) }).description).toMatch(/3,000/);
  });

  it("rejects a preferred visit in the past or ending before it starts", () => {
    const local = (ms: number) => new Date(ms - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
    const day = 86_400_000;
    const past = validateRequestForm({
      ...valid,
      preferred_start_at: local(Date.now() - 60 * day),
      preferred_end_at: local(Date.now() - 59 * day),
    });
    expect(past.preferred_end_at).toMatch(/future/);
    const inverted = validateRequestForm({
      ...valid,
      preferred_start_at: local(Date.now() + 3 * day),
      preferred_end_at: local(Date.now() + 2 * day),
    });
    expect(inverted.preferred_end_at).toMatch(/after the start/);
    expect(
      validateRequestForm({
        ...valid,
        preferred_start_at: local(Date.now() + 2 * day),
        preferred_end_at: local(Date.now() + 3 * day),
      }),
    ).toEqual({});
  });

  it("requires a category and a property", () => {
    const errors = validateRequestForm({ ...valid, category_id: "", property_id: "" });
    expect(errors.category_id).toBeDefined();
    expect(errors.property_id).toBeDefined();
  });
});

describe("request form", () => {
  beforeEach(() => signIn("REQUESTER"));

  it("shows inline errors and sends nothing when required fields are missing", async () => {
    const { calls } = mockFetch(
      (url) => (url.pathname.endsWith("/categories") ? { body: [] } : undefined),
      (url) => (url.pathname.endsWith("/properties") ? { body: emptyPage } : undefined),
    );
    renderWithProviders(<RequestForm />);
    await userEvent.click(screen.getByRole("button", { name: /submit report/i }));

    expect(await screen.findByText("Title is required.")).toBeInTheDocument();
    expect(screen.getByText("Description is required.")).toBeInTheDocument();
    expect(screen.getByText("Choose a category.")).toBeInTheDocument();
    expect(screen.getByText("Choose a property.")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveAttribute("aria-invalid", "true");
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(false));
  });

  it("clears the error once the field is valid and describes limits in a hint", async () => {
    mockFetch(
      (url) => (url.pathname.endsWith("/categories") ? { body: [] } : undefined),
      (url) => (url.pathname.endsWith("/properties") ? { body: emptyPage } : undefined),
    );
    renderWithProviders(<RequestForm />);
    await userEvent.type(screen.getByLabelText("Title"), "Hi");
    await userEvent.click(screen.getByRole("button", { name: /submit report/i }));
    expect(await screen.findByText(/at least 5 characters/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Title"), " there, boiler");
    await userEvent.click(screen.getByRole("button", { name: /submit report/i }));
    await waitFor(() => expect(screen.queryByText(/Title must be/)).not.toBeInTheDocument());
  });
});
