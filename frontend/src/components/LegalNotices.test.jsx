import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import LegalNotices from "./LegalNotices";

test("opens the privacy notice with processors and deletion information", () => {
  render(<LegalNotices />);

  fireEvent.click(screen.getByRole("button", { name: "개인정보처리방침" }));

  const dialog = screen.getByRole("dialog", { name: "개인정보처리방침" });
  expect(dialog).toHaveTextContent("Supabase");
  expect(dialog).toHaveTextContent("Google Gemini");
  expect(dialog).toHaveTextContent("계정 삭제");
  fireEvent.click(screen.getByRole("button", { name: "안내 닫기" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("explains the limits of the free beta and medical advice", () => {
  render(<LegalNotices />);

  fireEvent.click(screen.getByRole("button", { name: "베타 이용 안내" }));

  const dialog = screen.getByRole("dialog", { name: "베타 이용 안내" });
  expect(dialog).toHaveTextContent("의료 진단");
  expect(dialog).toHaveTextContent("무료 베타");
  expect(dialog).toHaveTextContent("민감정보");
});
