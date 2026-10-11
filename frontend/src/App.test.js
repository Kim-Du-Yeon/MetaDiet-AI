import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import App from "./App";
import { supabase } from "./lib/supabaseClient";

jest.mock("./lib/supabaseClient", () => ({
  supabase: { auth: {
    getSession: jest.fn(),
    onAuthStateChange: jest.fn(() => ({ data: { subscription: { unsubscribe: jest.fn() } } })),
    signOut: jest.fn(),
  } },
}));
jest.mock("./api/dietApi", () => ({ setToken: jest.fn() }));

beforeEach(() => {
  supabase.auth.onAuthStateChange.mockReturnValue({
    data: { subscription: { unsubscribe: jest.fn() } },
  });
});

test("shows an accessible loading state while authentication is restored", () => {
  supabase.auth.getSession.mockReturnValue(new Promise(() => {}));
  render(<App />);
  expect(screen.getByRole("status")).toHaveTextContent("안전하게 세션을 확인하는 중");
});

test("returns to authentication when an API reports an expired session", async () => {
  supabase.auth.getSession.mockResolvedValue({ data: { session: { access_token: "expired" } } });
  supabase.auth.signOut.mockResolvedValue({ error: null });
  render(<App />);
  window.dispatchEvent(new Event("metadiet:auth-expired"));
  expect(await screen.findByRole("form", { name: "계정 로그인" })).toBeInTheDocument();
  expect(supabase.auth.signOut).toHaveBeenCalledTimes(1);
});
