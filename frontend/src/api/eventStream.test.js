import { TextDecoder, TextEncoder } from "util";
import { consumeEventStream } from "./eventStream";

global.TextDecoder = TextDecoder;

test('reader errors retain the last sequence to avoid duplicate tokens on retry', async () => {
  const reader = { read: jest.fn().mockResolvedValueOnce({ done: false,
    value: new TextEncoder().encode('data: {"type":"answer_delta","seq":8,"content":"답변"}\n\n')
  }).mockRejectedValueOnce(new TypeError('network lost')), cancel: async () => {}, releaseLock: () => {} };
  await expect(consumeEventStream({ ok: true, body: { getReader: () => reader } }, () => {}))
    .rejects.toMatchObject({ lastSeq: 8 });
});

test('completed is authoritative even if the connection would fail immediately after it', async () => {
  const reader = { read: jest.fn().mockResolvedValueOnce({ done: false,
    value: new TextEncoder().encode('data: {"type":"completed","seq":9,"answer":"완료"}\n\n')
  }).mockRejectedValueOnce(new TypeError('network lost')), cancel: async () => {}, releaseLock: () => {} };
  await expect(consumeEventStream({ ok: true, body: { getReader: () => reader } }, () => {})).resolves.toBe(9);
  expect(reader.read).toHaveBeenCalledTimes(1);
});
function response(text) {
  const bytes = new TextEncoder().encode(text);
  let index = 0;
  return { ok: true, body: { getReader: () => ({
    read: async () => index < bytes.length
      ? { value: bytes.slice(index, ++index), done: false } : { done: true },
    cancel: async () => {}, releaseLock: () => {},
  }) } };
}

test("one-byte chunks preserve Korean, JSON and CRLF frames", async () => {
  const events = [];
  await consumeEventStream(response(': heartbeat\r\n\r\ndata: {"type":"token","content":"식단 추천"}\r\n\r\ndata: {"type":"done"}\n\n'), e => events.push(e));
  expect(events).toEqual([{ type: "token", content: "식단 추천" }, { type: "done" }]);
});

test("connection loss is surfaced instead of silently dropping partial JSON", async () => {
  await expect(consumeEventStream(response('data: {"type":"tok'), () => {})).rejects.toThrow("완전히");
});

test("server error is surfaced", async () => {
  await expect(consumeEventStream(response('data: {"type":"error","content":"failed"}\n\n'), () => {})).rejects.toThrow("failed");
});

test("failed stream preserves its trace identifier for incident correlation", async () => {
  await expect(consumeEventStream(response(
    'data: {"type":"failed","content":"failed","trace_id":"root-span"}\n\n'
  ), () => {})).rejects.toMatchObject({ traceId: "root-span" });
});

test("HTTP failure is surfaced before reading body", async () => {
  await expect(consumeEventStream({ ok: false, status: 401 }, () => {})).rejects.toThrow("401");
});

test("HTTP 401 announces an expired authentication session", async () => {
  const listener = jest.fn();
  window.addEventListener("metadiet:auth-expired", listener);
  await expect(consumeEventStream({ ok: false, status: 401 }, () => {})).rejects.toThrow("401");
  expect(listener).toHaveBeenCalledTimes(1);
  window.removeEventListener("metadiet:auth-expired", listener);
});

test("duplicate or replayed sequence numbers are ignored", async () => {
  const events = [];
  const lastSeq = await consumeEventStream(response(
    'id: 2\ndata: {"type":"progress","seq":2}\n\n' +
    'id: 2\ndata: {"type":"progress","seq":2}\n\n' +
    'id: 100000\ndata: {"type":"completed","seq":100000}\n\n'
  ), event => events.push(event), { afterSeq: 1 });
  expect(events.map(event => event.seq)).toEqual([2, 100000]);
  expect(lastSeq).toBe(100000);
});

test("connection loss exposes the last received sequence for reconnect", async () => {
  let error;
  try {
    await consumeEventStream(response('data: {"type":"progress","seq":7}\n\n'), () => {});
  } catch (caught) { error = caught; }
  expect(error.message).toMatch("완전히");
  expect(error.lastSeq).toBe(7);
});
