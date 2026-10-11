import { TextDecoder, TextEncoder } from "util";
import { deleteAccount, getSessionRestore, sendChatMessage, setToken } from "./dietApi";

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
