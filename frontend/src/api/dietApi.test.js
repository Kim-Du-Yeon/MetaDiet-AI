import { TextDecoder, TextEncoder } from "util";
import { deleteAccount, getAdminAnalytics, getSessionRestore, recordProductEvent, sendChatMessage, setToken, submitBetaFeedback, updateMeal, deleteMeal } from "./dietApi";

global.TextDecoder = TextDecoder;

function streamResponse(text) {
  const bytes = new TextEncoder().encode(text);
  let sent = false;
  return { ok: true, body: { getReader: () => ({
    read: async () => sent ? { done: true } : (sent = true, { value: bytes, done: false }),
    cancel: async () => {}, releaseLock: () => {},
  }) } };
}

afterEach(() => jest.restoreAllMocks());

test('failed meal writes reject instead of triggering success refresh', async()=>{
  global.fetch=jest.fn().mockResolvedValue({ok:false,status:409,json:async()=>({detail:'기록이 변경됐습니다.'})});
  await expect(updateMeal('test',20)).rejects.toThrow('기록이 변경됐습니다.');
  await expect(deleteMeal('test')).rejects.toThrow('기록이 변경됐습니다.');
});

test("transport failure reconnects once with the same stream run id", async () => {
  const completed = { type: "completed", seq: 100000, run_id: "server-echo" };
  global.fetch = jest.fn()
    .mockRejectedValueOnce(new TypeError("network down"))
    .mockResolvedValueOnce(streamResponse(`data: ${JSON.stringify(completed)}\n\n`));
  const done = jest.fn();

  await sendChatMessage("ignored", "저녁 추천", jest.fn(), done);

  expect(global.fetch).toHaveBeenCalledTimes(2);
  const first = JSON.parse(global.fetch.mock.calls[0][1].body);
  const second = JSON.parse(global.fetch.mock.calls[1][1].body);
  expect(second.stream_run_id).toBe(first.stream_run_id);
  expect(global.fetch.mock.calls[0][1].headers['X-Request-ID']).toBe(first.stream_run_id);
  expect(global.fetch.mock.calls[1][1].headers['X-Request-ID']).toBe(first.stream_run_id);
  expect(global.fetch.mock.calls[1][1].headers['X-Attempt-ID']).not.toBe(global.fetch.mock.calls[0][1].headers['X-Attempt-ID']);
  expect(second.after_seq).toBe(0);
  expect(done).toHaveBeenCalledWith(completed);
});

test("deleteAccount sends explicit confirmation with the current bearer token", async () => {
  setToken("fresh-token");
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: "deleted" }),
  });

  await expect(deleteAccount()).resolves.toEqual({ status: "deleted" });

  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining("/users/me"),
    expect.objectContaining({
      method: "DELETE",
      headers: expect.objectContaining({
        Authorization: "Bearer fresh-token",
        "Content-Type": "application/json",
      }),
      body: JSON.stringify({ confirmation: "DELETE" }),
    })
  );
});

test("deleteAccount preserves retryable partial failure details", async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: false,
    status: 503,
    json: async () => ({
      detail: {
        code: "auth_deletion_pending",
        message: "인증 계정 삭제를 재시도해야 합니다.",
        retryable: true,
      },
    }),
  });

  await expect(deleteAccount()).rejects.toMatchObject({
    code: "auth_deletion_pending",
    retryable: true,
    status: 503,
  });
});

test("getSessionRestore treats a missing first session as an empty state", async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: false,
    status: 404,
    json: async () => ({ detail: "Not Found" }),
  });

  await expect(getSessionRestore("new-thread")).resolves.toEqual({
    messages: [],
    pending_state: {},
    pending_proposal: null,
    interrupted: false,
  });
});

test("getSessionRestore announces an expired authentication session", async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: false,
    status: 401,
    json: async () => ({ detail: "expired" }),
  });
  const listener = jest.fn();
  window.addEventListener("metadiet:auth-expired", listener);

  await expect(getSessionRestore("expired-thread")).rejects.toThrow("expired");
  expect(listener).toHaveBeenCalledTimes(1);

  window.removeEventListener("metadiet:auth-expired", listener);
});

test("submitBetaFeedback sends the exact authenticated contract", async () => {
  setToken("feedback-token");
  const payload = {
    rating: 4,
    category: "evidence",
    comment: "근거가 유용해요",
    client_submission_id: "11111111-1111-1111-1111-111111111111",
  };
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ id: "feedback-1", status: "stored", created: true }),
  });

  await expect(submitBetaFeedback(payload)).resolves.toEqual({
    id: "feedback-1",
    status: "stored",
    created: true,
  });

  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining("/feedback"),
    {
      method: "POST",
      headers: {
        Authorization: "Bearer feedback-token",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
});

test("submitBetaFeedback surfaces a retryable generic error without mutating payload", async () => {
  const payload = {
    rating: 2,
    category: "bug",
    comment: "입력은 유지되어야 함",
    client_submission_id: "22222222-2222-2222-2222-222222222222",
  };
  const snapshot = { ...payload };
  global.fetch = jest.fn().mockResolvedValue({
    ok: false,
    status: 503,
    json: async () => ({ detail: "피드백 저장 서비스를 잠시 사용할 수 없습니다." }),
  });

  await expect(submitBetaFeedback(payload)).rejects.toMatchObject({
    message: "피드백 저장 서비스를 잠시 사용할 수 없습니다.",
    retryable: true,
    status: 503,
  });
  expect(payload).toEqual(snapshot);
  expect(global.fetch).toHaveBeenCalledTimes(1);
});

test("recordProductEvent sends only the allowlisted analytics contract", async () => {
  setToken("analytics-token");
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ id: "e1", created: true }) });
  await recordProductEvent("chat_completed", {
    clientEventId: "11111111-1111-4111-8111-111111111111",
    durationMs: 1250.4,
    properties: { route: "meal_plan" },
  });
  const body = JSON.parse(global.fetch.mock.calls[0][1].body);
  expect(body).toEqual(expect.objectContaining({
    event_name: "chat_completed", status: "success", duration_ms: 1250,
    properties: { route: "meal_plan" },
  }));
  expect(body).not.toHaveProperty("message");
});

test("getAdminAnalytics hides the operations panel for ordinary users", async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({}) });
  await expect(getAdminAnalytics(7)).resolves.toBeNull();
});
