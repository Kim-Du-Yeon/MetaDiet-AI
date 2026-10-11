/** Decode SSE across arbitrary UTF-8 and frame boundaries. */
export async function consumeEventStream(response, onEvent, { afterSeq = 0 } = {}) {
  if (!response.ok) throw new Error(`요청 실패 (${response.status})`);
  if (!response.body) throw new Error("스트리밍 응답이 없습니다.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  let lastSeq = afterSeq;
  function dispatch(frame) {
    const data = frame.split(/\r?\n/)
      .filter(line => line.startsWith("data:"))
      .map(line => line.slice(5).replace(/^ /, ""))
      .join("\n");
    if (!data) return; // comments/keepalives
    const event = JSON.parse(data);
    if (event.type === "error" || event.type === "failed") {
      throw new Error(event.content || "처리 중 오류가 발생했습니다.");
    }
    if (event.type === "done" || event.type === "completed") completed = true;
    if (Number.isInteger(event.seq)) {
      if (event.seq <= lastSeq) return;
      lastSeq = event.seq;
    }
    onEvent(event);
  }
  function drain() {
    let separator;
    while ((separator = /\r?\n\r?\n/.exec(buffer))) {
      dispatch(buffer.slice(0, separator.index));
      buffer = buffer.slice(separator.index + separator[0].length);
    }
  }
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      drain();
    }
    buffer += decoder.decode();
    drain();
    if (buffer.trim() || !completed) {
      const error = new Error("연결이 종료되어 응답을 완전히 받지 못했습니다.");
      error.lastSeq = lastSeq;
      throw error;
    }
    return lastSeq;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
