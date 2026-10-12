import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import ChatInterface from "./ChatInterface";
import { sendChatMessage, getSessionRestore } from "../../api/dietApi";

jest.mock("../../api/dietApi", () => ({
  sendChatMessage: jest.fn(), uploadImage: jest.fn(), resumeChat: jest.fn(),
  getChatHistory: jest.fn(), rollbackToCheckpoint: jest.fn(), nutritionLookup: jest.fn(),
  decideProposal: jest.fn(), reviseMeasurement: jest.fn(), getSessionRestore: jest.fn(),
  trackProductEvent: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  getSessionRestore.mockResolvedValue({ messages: [], pending_state: {}, pending_proposal: null });
});

function Harness() {
  const React = require("react");
  const [messages, setMessages] = React.useState([{ role: "assistant", content: "안녕하세요" }]);
  const [threadId, setThreadId] = React.useState("thread");
  const [previous, setPrevious] = React.useState(null);
  const [interrupted, setInterrupted] = React.useState(false);
  const [stats, setStats] = React.useState(null);
  return <><span data-testid="stats">{stats ? `${stats.calories}/${stats.target}` : ""}</span>
    <ChatInterface messages={messages} setMessages={setMessages}
      threadId={threadId} setThreadId={setThreadId} prevThreadId={previous} setPrevThreadId={setPrevious}
      isInterrupted={interrupted} setIsInterrupted={setInterrupted} onStatsUpdate={setStats} /></>;
}

test("renders streamed backend phases with the completed answer", async () => {
  sendChatMessage.mockImplementation(async (_user, _message, onToken, onDone, _pending, _messages, _thread, _meal, onProgress) => {
    onProgress({ phase: "intent", label: "요청 의도 분석 중" });
    onProgress({ phase: "evidence", label: "근거 자료 검색 중" });
    onToken("근거를 반영한 답변");
    onDone({ agent_used: "strategy", awaiting_confirmation: false });
  });
  render(<Harness />);
  fireEvent.change(screen.getByPlaceholderText("오늘 뭐 드셨어요?"), { target: { value: "저녁 추천해줘" } });
  fireEvent.click(screen.getByRole("button", { name: "전송" }));

  await waitFor(() => expect(screen.getByText("근거를 반영한 답변")).toBeInTheDocument());
  expect(screen.getByText("검토 과정 2단계")).toBeInTheDocument();
  expect(screen.getByText("근거 자료 검색 중")).toBeInTheDocument();
});

test("restores recent messages and a pending proposal without rerunning chat", async () => {
  getSessionRestore.mockResolvedValue({
    messages: [
      { role: "user", content: "저녁 추천" },
      { role: "assistant", content: "확인해주세요", agent_used: "meal" },
    ],
    pending_state: { pending_meals: [], awaiting_confirmation: true, plan_date: "2026-10-11" },
    pending_proposal: { id: "p1", version: 2, kind: "plan", status: "pending",
      payload: { kind: "plan", log_date: "2026-10-11", meals: [] } },
    interrupted: true,
    today_calories: 244.2,
    target_calories: 1800,
  });

  render(<Harness />);

  expect(await screen.findByText("저녁 추천")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "확인 대기 제안" })).toBeInTheDocument();
  expect(screen.getByTestId("stats")).toHaveTextContent("244.2/1800");
  expect(sendChatMessage).not.toHaveBeenCalled();
});

test("shows a restore status and recovers the screen without rerunning a completed request", async () => {
  let rejectRestore;
  getSessionRestore.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectRestore = reject; }))
    .mockResolvedValueOnce({
      messages: [{ role: "assistant", content: "복원된 답변" }],
      pending_state: {}, pending_proposal: null, today_calories: 120, target_calories: 1800,
    });

  render(<Harness />);
  expect(screen.getByRole("status")).toHaveTextContent("이전 대화를 불러오는 중");
  rejectRestore(new Error("network down"));

  expect(await screen.findByRole("alert")).toHaveTextContent("이전 상태를 불러오지 못했습니다");
  fireEvent.click(screen.getByRole("button", { name: "화면 상태 다시 불러오기" }));

  expect(await screen.findByText("복원된 답변")).toBeInTheDocument();
  expect(getSessionRestore).toHaveBeenCalledTimes(2);
  expect(sendChatMessage).not.toHaveBeenCalled();
});

test("empty chat suggestions prepare a request without sending it", async () => {
  render(<Harness />);
  fireEvent.click(await screen.findByRole("button", { name: "오늘 저녁 추천받기" }));

  expect(screen.getByLabelText("식단 코치에게 메시지 보내기")).toHaveValue("오늘 저녁 식단을 추천해줘");
  expect(sendChatMessage).not.toHaveBeenCalled();
});

test("keeps the conversation usable when a streamed request is interrupted", async () => {
  sendChatMessage.mockRejectedValue(new Error("네트워크 연결이 끊어졌습니다."));
  render(<Harness />);
  fireEvent.change(screen.getByPlaceholderText("오늘 뭐 드셨어요?"), { target: { value: "저녁 추천해줘" } });
  fireEvent.click(screen.getByRole("button", { name: "전송" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("네트워크 연결이 끊어졌습니다.");
  expect(screen.getByText("응답을 끝까지 받지 못했습니다. 잠시 후 다시 요청해주세요.")).toBeInTheDocument();
  const composer = screen.getByLabelText("식단 코치에게 메시지 보내기");
  fireEvent.change(composer, { target: { value: "다시 시도" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "전송" })).not.toBeDisabled());
});
