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
