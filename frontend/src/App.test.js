import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import App from "./App";
import { supabase } from "./lib/supabaseClient";

jest.mock("./lib/supabaseClient", () => ({
  supabase: { auth: {
    getSession: jest.fn(),
    onAuthStateChange: jest.fn(() => ({ data: { subscription: { unsubscribe: jest.fn() } } })),
  } },
}));
jest.mock("./api/dietApi", () => ({ setToken: jest.fn() }));

test("shows an accessible loading state while authentication is restored", () => {
  supabase.auth.getSession.mockReturnValue(new Promise(() => {}));
  supabase.auth.onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: jest.fn() } } });
  render(<App />);
  expect(screen.getByRole("status")).toHaveTextContent("안전하게 세션을 확인하는 중");
});
