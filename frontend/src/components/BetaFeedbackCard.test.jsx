import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import BetaFeedbackCard from "./BetaFeedbackCard";
import { submitBetaFeedback } from "../api/dietApi";

jest.mock("../api/dietApi", () => ({ submitBetaFeedback: jest.fn() }));

beforeEach(() => jest.clearAllMocks());

function completeForm() {
  fireEvent.click(screen.getByRole("radio", { name: "4점" }));
  fireEvent.change(screen.getByLabelText("피드백 종류"), {
    target: { value: "answer_quality" },
  });
  fireEvent.change(screen.getByLabelText("의견 (선택)"), {
    target: { value: "답변이 유용했어요" },
  });
}

test("renders accessible rating, category, privacy copy and character count", () => {
  render(<BetaFeedbackCard uuidFactory={() => "submission-1"} />);

  expect(screen.getByRole("group", { name: "서비스 만족도" })).toBeTruthy();
  expect(screen.getByRole("radio", { name: "1점" })).toBeTruthy();
  expect(screen.getByLabelText("피드백 종류")).toBeTruthy();
  expect(screen.getByText(/대화·식사·인바디 기록은 자동으로 첨부되지 않습니다/)).toBeTruthy();
  expect(screen.getByText("0 / 1000")).toBeTruthy();

  fireEvent.change(screen.getByLabelText("의견 (선택)"), {
    target: { value: "가".repeat(1000) },
  });
  expect(screen.getByText("1000 / 1000")).toBeTruthy();
});

test("requires a rating before submission", async () => {
  render(<BetaFeedbackCard uuidFactory={() => "submission-1"} />);

  fireEvent.click(screen.getByRole("button", { name: "피드백 보내기" }));

  expect(await screen.findByText("만족도를 선택해주세요.")).toBeTruthy();
  expect(submitBetaFeedback).not.toHaveBeenCalled();
});

test("locks duplicate clicks and resets after success", async () => {
  let resolveRequest;
  submitBetaFeedback.mockReturnValue(
    new Promise((resolve) => { resolveRequest = resolve; })
  );
  render(<BetaFeedbackCard uuidFactory={() => "submission-1"} />);
  completeForm();

  const button = screen.getByRole("button", { name: "피드백 보내기" });
  fireEvent.click(button);
  fireEvent.click(button);

  expect(submitBetaFeedback).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "전송 중..." }).disabled).toBe(true);
  resolveRequest({ id: "feedback-1", status: "stored", created: true });

  expect(await screen.findByText("피드백을 보내주셔서 감사합니다.")).toBeTruthy();
  expect(screen.getByLabelText("의견 (선택)").value).toBe("");
  expect(screen.getByLabelText("피드백 종류").value).toBe("general");
  expect(screen.getByRole("radio", { name: "4점" }).checked).toBe(false);
});

test("retains input and reuses the submission id after failure", async () => {
  submitBetaFeedback
    .mockRejectedValueOnce(new Error("temporary"))
    .mockResolvedValueOnce({ id: "feedback-2", status: "stored", created: true });
  render(<BetaFeedbackCard uuidFactory={() => "stable-submission"} />);
  completeForm();

  fireEvent.click(screen.getByRole("button", { name: "피드백 보내기" }));
  expect(await screen.findByText(/전송하지 못했습니다/)).toBeTruthy();
  expect(screen.getByLabelText("의견 (선택)").value).toBe("답변이 유용했어요");

  fireEvent.click(screen.getByRole("button", { name: "피드백 보내기" }));
  await waitFor(() => expect(submitBetaFeedback).toHaveBeenCalledTimes(2));
  expect(submitBetaFeedback.mock.calls[0][0].client_submission_id).toBe("stable-submission");
  expect(submitBetaFeedback.mock.calls[1][0].client_submission_id).toBe("stable-submission");
});
