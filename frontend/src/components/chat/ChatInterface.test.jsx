import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import ChatInterface from "./ChatInterface";
import { sendChatMessage, getSessionRestore, trackProductEvent, resolveMealChoices, decideProposal, resumeChat, nutritionLookup, reviseMeal } from "../../api/dietApi";

jest.mock("../../api/dietApi", () => ({
  sendChatMessage: jest.fn(), uploadImage: jest.fn(), resumeChat: jest.fn(),
  getChatHistory: jest.fn(), rollbackToCheckpoint: jest.fn(), nutritionLookup: jest.fn(),
  decideProposal: jest.fn(), reviseMeasurement: jest.fn(), getSessionRestore: jest.fn(),
  trackProductEvent: jest.fn(), resolveMealChoices:jest.fn(), reviseMeal:jest.fn(),
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
  expect(screen.queryByRole('button',{name:'점심 추천'})).not.toBeInTheDocument();
});

test('chat confirmation shows recommendations only with server-confirmed intake metadata', async () => {
  const payload = {log_date:'2026-10-19',meals:[{food_name:'밥',quantity_g:200,calories:300,carbs_g:65,protein_g:5,fat_g:1,source:'csv'}]};
  getSessionRestore.mockResolvedValue({messages:[],pending_state:{},pending_proposal:{id:'p',version:1,kind:'intake',payload}});
  resumeChat.mockImplementation(async (_user,_thread,_message,_token,done)=>done({answer:'실제 섭취 기록을 확정했습니다.',intake_confirmed:true,pending_proposal:null}));
  render(<Harness />);
  fireEvent.click(await screen.findByRole('button',{name:'이대로 기록'}));
  await screen.findByRole('button',{name:'점심 추천'});
  expect(screen.getByRole('button',{name:'저녁 추천'})).toBeVisible();
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
  getSessionRestore.mockResolvedValue({messages:[],pending_state:{},proposal_decision_mode:'direct',pending_proposal:{id:'p',version:1,kind:'intake',payload:{log_date:'2026-10-19',meals:[{food_name:'밥',quantity_g:200,calories:300,carbs_g:65,protein_g:5,fat_g:1,source:'csv'}]}}});
  decideProposal.mockResolvedValue({status:'confirmed'});
  sendChatMessage.mockImplementation(async (_user, _message, onToken, onDone) => {
    onToken('중간 답변');
    onDone({ answer: '**최종 답변**', execution_status: 'completed' });
  });
  render(<Harness />);
  fireEvent.click(await screen.findByRole('button', {name:'이대로 기록'}));
  fireEvent.click(await screen.findByRole('button', { name: '점심 추천' }));
  await screen.findByText('최종 답변');
  expect(screen.queryByText('중간 답변')).not.toBeInTheDocument();
  expect(sendChatMessage.mock.calls[0][1]).toBe('점심 추천해줘');
});

test('initial screen hides product and recommendation shortcuts', async () => {
  render(<Harness />);
  await waitFor(() => expect(screen.getByPlaceholderText('오늘 뭐 드셨어요?')).toBeEnabled());
  expect(screen.queryByRole('button',{name:'제품 영양표 입력'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'제품을 정확히 입력'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'점심 추천'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'저녁 추천'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'오늘 저녁 추천받기'})).not.toBeInTheDocument();
});

test('product tools are optional inside intake card and cancellation never shows recommendations', async () => {
  getSessionRestore.mockResolvedValue({messages:[],pending_state:{},proposal_decision_mode:'direct',pending_proposal:{id:'p',version:1,kind:'intake',payload:{log_date:'2026-10-19',meals:[{food_name:'밥',quantity_g:200,calories:300,carbs_g:65,protein_g:5,fat_g:1,source:'csv'}]}}});
  decideProposal.mockResolvedValue({status:'cancelled'});
  render(<Harness />);
  fireEvent.click(await screen.findByRole('button',{name:'정확한 제품으로 변경 (선택)'}));
  const {within} = require('@testing-library/react');
  expect(within(screen.getByRole('region',{name:'확인 대기 제안'})).getByRole('button',{name:'제품 영양표 입력'})).toBeVisible();
  expect(screen.getByRole('button',{name:'이대로 기록'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'취소',exact:true}));
  await screen.findByText('제안을 취소했습니다.');
  expect(screen.queryByRole('button',{name:'점심 추천'})).not.toBeInTheDocument();
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

test("empty chat explains free text input without sending or suggesting a meal", async () => {
  render(<Harness />);
  await screen.findByText(/제육볶음이랑 밥 먹었어/);
  expect(screen.getByLabelText("식단 코치에게 메시지 보내기")).toHaveValue("");
  expect(sendChatMessage).not.toHaveBeenCalled();
});

test('exact product replacement keeps the other meal and does not confirm or rerun Agent', async () => {
  const payload = {log_date:'2026-10-19',meals:[
    {food_id:'csv:rice',food_name:'밥',quantity_g:200,calories:300,carbs_g:65,protein_g:5,fat_g:1,source:'csv',meal_type:'lunch'},
    {food_id:'csv:chicken',food_name:'닭가슴살',quantity_g:100,calories:160,carbs_g:0,protein_g:30,fat_g:4,source:'csv',meal_type:'lunch'}]};
  getSessionRestore.mockResolvedValue({messages:[],pending_state:{},pending_proposal:{id:'p',version:1,kind:'intake',payload}});
  nutritionLookup.mockResolvedValue({results:[{status:'ambiguous',candidates:[{food_id:'mfds:P1',name:'정확한 제품',manufacturer:'검증 제조사'}]}]});
  reviseMeal.mockResolvedValue({id:'p2',version:2,kind:'intake',payload:{...payload,meals:[payload.meals[0],{...payload.meals[1],food_id:'mfds:P1',food_name:'정확한 제품',source:'mfds'}]}});
  render(<Harness />);
  fireEvent.click(await screen.findByRole('button',{name:'정확한 제품으로 변경 (선택)'}));
  expect(screen.getByLabelText('1번 음식 분량')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('변경할 음식'),{target:{value:'1'}});
  fireEvent.click(screen.getByRole('button',{name:'제품을 정확히 입력'}));
  expect(screen.getByLabelText('먹은 양 (g)')).toHaveValue(100);
  fireEvent.click(screen.getByRole('button',{name:'제품 검색'}));
  fireEvent.click(await screen.findByRole('button',{name:'이 제품 선택'}));
  await screen.findByText('정확한 제품');
  expect(reviseMeal.mock.calls[0][1]).toEqual({log_date:payload.log_date,meal_type:null,
    items:[{amount:200,unit:'g'},{food_id:'mfds:P1',amount:100,unit:'g'}]});
  expect(decideProposal).not.toHaveBeenCalled();
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
