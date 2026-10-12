import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import Auth from "./Auth";
import { supabase } from "../lib/supabaseClient";

jest.mock("../lib/supabaseClient", () => ({
  supabase: { auth: { signInWithPassword: jest.fn(), signUp: jest.fn() } },
}));

test("submits login with the keyboard and exposes errors accessibly", async () => {
  supabase.auth.signInWithPassword.mockResolvedValue({ error: { message: "로그인 정보가 올바르지 않습니다." } });
  render(<Auth />);

  fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "person@example.com" } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "wrong-password" } });
  fireEvent.submit(screen.getByRole("form", { name: "계정 로그인" }));

  await waitFor(() => expect(supabase.auth.signInWithPassword).toHaveBeenCalledWith({
    email: "person@example.com", password: "wrong-password",
  }));
  expect(await screen.findByRole("alert")).toHaveTextContent("로그인 정보가 올바르지 않습니다.");
});

test("makes privacy and beta notices available before login", () => {
  render(<Auth />);
  expect(screen.getByRole("button", { name: "개인정보처리방침" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "베타 이용 안내" })).toBeInTheDocument();
});

test("returns email confirmations to the current app origin", async () => {
  supabase.auth.signUp.mockResolvedValue({ error: null });
  render(<Auth />);

  fireEvent.click(screen.getByRole("tab", { name: "회원가입" }));
  fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "new@example.com" } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "safe-password" } });
  fireEvent.submit(screen.getByRole("form", { name: "계정 만들기" }));

  await waitFor(() => expect(supabase.auth.signUp).toHaveBeenCalledWith({
    email: "new@example.com",
    password: "safe-password",
    options: { emailRedirectTo: window.location.origin },
  }));
});
