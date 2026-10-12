import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Settings from "./Settings";
import { supabase } from "../lib/supabaseClient";
import { deleteAccount, setToken } from "../api/dietApi";

jest.mock("../lib/supabaseClient", () => ({
  supabase: { auth: { signInWithPassword: jest.fn(), signOut: jest.fn() } },
}));
jest.mock("../api/dietApi", () => ({
  deleteAccount: jest.fn(),
  setToken: jest.fn(),
  submitBetaFeedback: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  supabase.auth.signInWithPassword.mockResolvedValue({
    data: { session: { access_token: "fresh-token" } },
    error: null,
  });
  supabase.auth.signOut.mockResolvedValue({ error: null });
  deleteAccount.mockResolvedValue({ status: "deleted" });
});

test("requires password and DELETE before account deletion", async () => {
  const onDeleted = jest.fn();
  render(<Settings session={{ user: { email: "member@example.com" } }} onDeleted={onDeleted} />);

  fireEvent.click(screen.getByRole("button", { name: "계정 영구 삭제" }));

  expect(await screen.findByText("비밀번호와 DELETE 확인값을 입력해주세요.")).toBeTruthy();
  expect(supabase.auth.signInWithPassword).not.toHaveBeenCalled();
  expect(deleteAccount).not.toHaveBeenCalled();
});

test("account deletion password belongs to a submit form", () => {
  render(<Settings session={{ user: { email: "member@example.com" } }} onDeleted={jest.fn()} />);

  const form = screen.getByLabelText("현재 비밀번호").closest("form");
  expect(form).not.toBeNull();
  expect(form.querySelector('button[type="submit"]')?.textContent).toBe("계정 영구 삭제");
});

test("reauthenticates, switches to fresh token, deletes and clears stored sessions", async () => {
  window.localStorage.setItem("sb-project-auth-token", "synthetic-session");
  window.sessionStorage.setItem("sb-project-auth-token", "synthetic-session");
  const onDeleted = jest.fn();
  render(<Settings session={{ user: { email: "member@example.com" } }} onDeleted={onDeleted} />);
  fireEvent.change(screen.getByLabelText("현재 비밀번호"), { target: { value: "correct-password" } });
  fireEvent.change(screen.getByLabelText("삭제 확인"), { target: { value: "DELETE" } });
  fireEvent.click(screen.getByRole("button", { name: "계정 영구 삭제" }));

  await waitFor(() => expect(deleteAccount).toHaveBeenCalledTimes(1));
  expect(supabase.auth.signInWithPassword).toHaveBeenCalledWith({
    email: "member@example.com",
    password: "correct-password",
  });
  expect(setToken).toHaveBeenCalledWith("fresh-token");
  expect(window.localStorage.getItem("sb-project-auth-token")).toBeNull();
  expect(window.sessionStorage.getItem("sb-project-auth-token")).toBeNull();
  expect(supabase.auth.signOut).not.toHaveBeenCalled();
  expect(onDeleted).toHaveBeenCalledTimes(1);
});

test("keeps the retry path visible when only auth deletion is pending", async () => {
  deleteAccount.mockRejectedValue(Object.assign(new Error("인증 삭제 재시도 필요"), {
    code: "auth_deletion_pending",
    retryable: true,
  }));
  render(<Settings session={{ user: { email: "member@example.com" } }} onDeleted={jest.fn()} />);
  fireEvent.change(screen.getByLabelText("현재 비밀번호"), { target: { value: "correct-password" } });
  fireEvent.change(screen.getByLabelText("삭제 확인"), { target: { value: "DELETE" } });
  fireEvent.click(screen.getByRole("button", { name: "계정 영구 삭제" }));

  expect(await screen.findByText(/서비스 데이터는 삭제됐지만/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "인증 계정 삭제 재시도" })).toBeTruthy();
  expect(supabase.auth.signOut).not.toHaveBeenCalled();
});

test("returns to password reauthentication if the partial-failure retry becomes stale", async () => {
  deleteAccount
    .mockRejectedValueOnce(Object.assign(new Error("재시도 필요"), {
      code: "auth_deletion_pending",
      retryable: true,
    }))
    .mockRejectedValueOnce(Object.assign(new Error("recent auth required"), {
      code: "recent_authentication_required",
      retryable: true,
    }));
  render(<Settings session={{ user: { email: "member@example.com" } }} onDeleted={jest.fn()} />);
  fireEvent.change(screen.getByLabelText("현재 비밀번호"), { target: { value: "correct-password" } });
  fireEvent.change(screen.getByLabelText("삭제 확인"), { target: { value: "DELETE" } });
  fireEvent.click(screen.getByRole("button", { name: "계정 영구 삭제" }));
  fireEvent.click(await screen.findByRole("button", { name: "인증 계정 삭제 재시도" }));

  expect(await screen.findByText(/비밀번호를 다시 입력/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "계정 영구 삭제" })).toBeTruthy();
  expect(screen.getByLabelText("현재 비밀번호").disabled).toBe(false);
});

test("keeps service notices available from account settings", () => {
  render(<Settings session={{ user: { email: "member@example.com" } }} onDeleted={jest.fn()} />);
  expect(screen.getByRole("button", { name: "개인정보처리방침" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "베타 이용 안내" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "베타 피드백" })).toBeTruthy();
  expect(
    screen.getByRole("heading", { name: "베타 피드백" })
      .closest("section").nextElementSibling.getAttribute("aria-labelledby")
  ).toBe("delete-account-title");
});
