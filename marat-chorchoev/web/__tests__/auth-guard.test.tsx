import { screen, waitFor } from "@testing-library/react";
import { AuthGuard } from "@/components/auth-guard";
import { api } from "@/lib/api";
import { getSession } from "@/lib/session";
import { mockFetch, renderWithProviders, signIn, signOut } from "./utils";

const replace = jest.fn();
jest.mock("next/navigation", () => ({ useRouter: () => ({ replace, push: jest.fn() }) }));

describe("protected routes", () => {
  beforeEach(() => {
    replace.mockClear();
    signOut();
  });

  it("redirects to sign-in and renders nothing protected when signed out", async () => {
    renderWithProviders(
      <AuthGuard>
        <p>secret dashboard</p>
      </AuthGuard>,
    );
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("secret dashboard")).not.toBeInTheDocument();
  });

  it("renders content for a signed-in user with an allowed role", async () => {
    signIn("ADMIN");
    renderWithProviders(
      <AuthGuard roles={["ADMIN"]}>
        <p>admin page</p>
      </AuthGuard>,
    );
    expect(await screen.findByText("admin page")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("explains a role mismatch instead of showing the screen", async () => {
    signIn("REQUESTER");
    renderWithProviders(
      <AuthGuard roles={["ADMIN"]}>
        <p>admin page</p>
      </AuthGuard>,
    );
    expect(await screen.findByText(/Not available for your role/)).toBeInTheDocument();
    expect(screen.queryByText("admin page")).not.toBeInTheDocument();
  });

  it("an expired server session (401) ends the local session", async () => {
    signIn("DISPATCHER");
    mockFetch(() => ({ status: 401, body: { error: { code: "SESSION_EXPIRED", message: "Session expired." } } }));
    await expect(api.get("/requests")).rejects.toMatchObject({ status: 401, code: "SESSION_EXPIRED" });
    expect(getSession()).toBeNull();
  });
});
