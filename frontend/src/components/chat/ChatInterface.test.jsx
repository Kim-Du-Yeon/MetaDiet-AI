import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import ChatInterface from "./ChatInterface";
import { sendChatMessage, getSessionRestore, trackProductEvent, resolveMealChoices, decideProposal, resumeChat } from "../../api/dietApi";

jest.mock("../../api/dietApi", () => ({
  sendChatMessage: jest.fn(), uploadImage: jest.fn(), resumeChat: jest.fn(),
  getChatHistory: jest.fn(), rollbackToCheckpoint: jest.fn(), nutritionLookup: jest.fn(),
  decideProposal: jest.fn(), reviseMeasurement: jest.fn(), getSessionRestore: jest.fn(),
  trackProductEvent: jest.fn(), resolveMealChoices:jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  Object.defineProperty(window, 'crypto', {configurable:true, value:{randomUUID:jest.fn(()=>'11111111-1111-4111-8111-111111111111')}});
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

test('closing an entirely excluded selection removes card without saving and permits another message', async () => {
  getSessionRestore.mockResolvedValue({messages:[], pending_state:{}, food_selection:{mode:'meal_choices',id:'choice',known_count:0,items:[
    {index:0,query:'미등록음식',quantity_g:100}]}});
  resolveMealChoices.mockResolvedValue({cancelled:true});
  render(<Harness />);
  fireEvent.click(await screen.findByRole('button',{name:'제외하기'}));
  fireEvent.click(screen.getByRole('button',{name:'기록 없이 닫기'}));
  await screen.findByText('기록하지 않고 닫았어요. 다른 식사를 입력할 수 있어요.');
  expect(screen.queryByRole('region',{name:'음식 기록 선택'})).not.toBeInTheDocument();
  expect(resolveMealChoices.mock.calls[0][0].cancel).toBe(true);
  expect(decideProposal).not.toHaveBeenCalled();
});

test('restoring a session prevents submission before history can replace the active turn', () => {
  getSessionRestore.mockImplementationOnce(() => new Promise(() => {}));
  render(<Harness />);
  expect(screen.getByRole('textbox',{name:'식단 코치에게 메시지 보내기'})).toBeDisabled();
});

test('restored cancellation is not labeled as a confirmed meal', async () => {
  getSessionRestore.mockResolvedValue({messages:[
    {role:'assistant', content:'실제 섭취 기록을 취소했습니다.', agent_used:'confirm'},
  ], pending_state:{}, pending_proposal:null});
  render(<Harness />);
  await screen.findByText('실제 섭취 기록을 취소했습니다.');
  expect(screen.queryByText('✅ 식단 확정')).not.toBeInTheDocument();
});

test('unknown food can be excluded by buttons with retry instead of typed answer', async () => {
  getSessionRestore.mockResolvedValue({messages:[], pending_state:{}, food_selection:{mode:'meal_choices',id:'choice',items:[
    {index:1,query:'돼지바',quantity_g:70,generic_available:true}]}});
  resolveMealChoices.mockRejectedValueOnce(new Error('조회 실패')).mockResolvedValueOnce({id:'p',version:1,kind:'intake',payload:{
    log_date:'2026-10-13',meals:[{food_name:'밥',quantity_g:200,calories:300,carbs_g:65,protein_g:5,fat_g:1,source:'csv'}]}});
  render(<Harness />);
  await screen.findByRole('button',{name:'제외하기'});
  fireEvent.click(screen.getByRole('button',{name:'제외하기'}));
  fireEvent.click(screen.getByRole('button',{name:'남은 음식 확인하기'}));
  await screen.findAllByText('조회 실패');
  fireEvent.click(screen.getByRole('button',{name:'남은 음식 확인하기'}));
  await screen.findByRole('button',{name:'이대로 기록'});
  expect(resolveMealChoices.mock.calls[0][0].choices).toEqual([{index:1,action:'exclude'}]);
  expect(resolveMealChoices.mock.calls[0][0].request_id).toBe(resolveMealChoices.mock.calls[1][0].request_id);
  expect(sendChatMessage).not.toHaveBeenCalled();
  decideProposal.mockResolvedValue({status:'confirmed'});
  fireEvent.click(screen.getByRole('button',{name:'이대로 기록'}));
  await waitFor(() => expect(decideProposal).toHaveBeenCalledTimes(1));
  expect(resumeChat).not.toHaveBeenCalled();
});

test('restored external meal proposal confirms directly without resuming a finished graph', async () => {
  getSessionRestore.mockResolvedValue({messages:[],pending_state:{},proposal_decision_mode:'direct',pending_proposal:{id:'p',version:1,kind:'intake',payload:{
    log_date:'2026-10-13',meals:[{food_name:'밥',quantity_g:200,calories:300,carbs_g:65,protein_g:5,fat_g:1,source:'csv'}]}}});
  decideProposal.mockResolvedValue({status:'confirmed'});
  render(<Harness />);
  fireEvent.click(await screen.findByRole('button',{name:'이대로 기록'}));
  await waitFor(() => expect(decideProposal).toHaveBeenCalledTimes(1));
  expect(resumeChat).not.toHaveBeenCalled();
  await screen.findByText('섭취 기록을 저장했습니다.');
  expect(screen.getByText('합계 300 kcal')).toBeInTheDocument();
  expect(screen.getByText(/밥 · 200g · 300 kcal/)).toBeInTheDocument();
});

test('failed confirmation keeps proposal and does not show a saved receipt', async () => {
  getSessionRestore.mockResolvedValue({messages:[],pending_state:{},proposal_decision_mode:'direct',pending_proposal:{id:'p',version:1,kind:'intake',payload:{
    log_date:'2026-10-13',meals:[{food_name:'밥',quantity_g:200,calories:300,carbs_g:65,protein_g:5,fat_g:1,source:'csv'}]}}});
  decideProposal.mockRejectedValueOnce(new Error('저장 실패'));
  render(<Harness />);
  fireEvent.click(await screen.findByRole('button',{name:'이대로 기록'}));
  await screen.findAllByText('저장 실패');
  expect(screen.queryByText('섭취 기록을 저장했습니다.')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'이대로 기록'})).toBeEnabled();
});

test("renders streamed backend phases with the completed answer", async () => {
  sendChatMessage.mockImplementation(async (_user, _message, onToken, onDone, _pending, _messages, _thread, _meal, onProgress) => {
    onProgress({ phase: "intent", label: "요청 의도 분석 중" });
    onProgress({ phase: "evidence", label: "근거 자료 검색 중" });
    onToken("근거를 반영한 답변");
    onDone({ agent_used: "strategy", awaiting_confirmation: false, trace_id: "actual-root-span" });
  });
  render(<Harness />);
  await waitFor(() => expect(screen.getByPlaceholderText("오늘 뭐 드셨어요?")).toBeEnabled());
  fireEvent.change(screen.getByPlaceholderText("오늘 뭐 드셨어요?"), { target: { value: "저녁 추천해줘" } });
  fireEvent.click(screen.getByRole("button", { name: "전송" }));

  await waitFor(() => expect(screen.getByText("근거를 반영한 답변")).toBeInTheDocument());
  expect(screen.getByText("검토 과정 2단계")).toBeInTheDocument();
  expect(screen.getByText("근거 자료 검색 중")).toBeInTheDocument();
  expect(trackProductEvent).toHaveBeenCalledWith("chat_completed", expect.objectContaining({
    traceId: "actual-root-span",
  }));
});

test('completed snapshot replaces partial text and recommendation buttons use the direct request', async () => {
  sendChatMessage.mockImplementation(async (_user, _message, onToken, onDone) => {
    onToken('중간 답변');
    onDone({ answer: '**최종 답변**', execution_status: 'completed' });
  });
  render(<Harness />);
  fireEvent.click(await screen.findByRole('button', { name: '점심 추천' }));
  await screen.findByText('최종 답변');
  expect(screen.queryByText('중간 답변')).not.toBeInTheDocument();
  expect(sendChatMessage.mock.calls[0][1]).toBe('점심 추천해줘');
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
  await waitFor(() => expect(screen.getByPlaceholderText("오늘 뭐 드셨어요?")).toBeEnabled());
  fireEvent.change(screen.getByPlaceholderText("오늘 뭐 드셨어요?"), { target: { value: "저녁 추천해줘" } });
  fireEvent.click(screen.getByRole("button", { name: "전송" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("네트워크 연결이 끊어졌습니다.");
  expect(screen.getByText("응답을 끝까지 받지 못했습니다. 잠시 후 다시 요청해주세요.")).toBeInTheDocument();
  const composer = screen.getByLabelText("식단 코치에게 메시지 보내기");
  fireEvent.change(composer, { target: { value: "다시 시도" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "전송" })).not.toBeDisabled());
});

test("restores product cards and sends complete meal request without showing IDs", async () => {
  getSessionRestore.mockResolvedValue({ messages: [], pending_state: {}, pending_proposal: null,
    food_selection: { request: "어제 쌀밥 450g과 라이스페이퍼 80g", items: [{query: "라이스페이퍼", quantity_g: 80,
      candidates: [{food_id: "mfds:P1", name: "라이스페이퍼", manufacturer: "테스트 제조사", package_text: "100g"}]}] } });
  sendChatMessage.mockResolvedValue(undefined);
  render(<Harness />);
  fireEvent.click(await screen.findByRole("radio"));
  fireEvent.click(screen.getByRole("button", {name: "선택한 제품으로 다시 검토"}));
  await waitFor(() => expect(sendChatMessage).toHaveBeenCalled());
  expect(sendChatMessage.mock.calls[0][1]).toContain("어제 쌀밥 450g");
  expect(sendChatMessage.mock.calls[0][1]).toContain("제품 선택: mfds:P1");
  expect(screen.queryByText(/mfds:P1/)).not.toBeInTheDocument();
});
