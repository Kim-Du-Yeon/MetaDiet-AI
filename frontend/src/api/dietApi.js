const BASE_URL = "http://localhost:8000";

export async function sendChatMessage(
  userId, message, onToken, onDone,
  pendingState = {}, messages = [], threadId = "default", mealType = null
) {
  const response = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      message,
      thread_id: threadId,
      pending_meals: pendingState.pending_meals || null,
      awaiting_confirmation: pendingState.awaiting_confirmation || false,
      plan_date: pendingState.plan_date || null,
      meal_type: mealType,   // 사용자가 버튼으로 고른 끼니(있으면 강제 적용)
      messages: messages.slice(-10).map(m => ({
        role: m.role,
        content: m.content,
      })),
    }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = decoder.decode(value);
    const lines = text.split("\n").filter((l) => l.startsWith("data: "));

    for (const line of lines) {
      try {
        const data = JSON.parse(line.replace("data: ", ""));
        if (data.type === "token") onToken(data.content);
        if (data.type === "done") onDone(data);
      } catch (e) {}
    }
  }
}

export async function getChatHistory(userId, threadId) {
  const res = await fetch(
    `${BASE_URL}/chat/history/${threadId}?user_id=${userId}`
  );
  return res.json();
}

export async function rollbackToCheckpoint(userId, threadId, checkpointId) {
  // 백엔드가 query param 방식으로 받음
  const res = await fetch(
    `${BASE_URL}/chat/rollback?user_id=${userId}&thread_id=${threadId}&checkpoint_id=${checkpointId}`,
    { method: "POST" }
  );
  return res.json();
}

export async function uploadInbody(userId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE_URL}/inbody/upload?user_id=${userId}`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "업로드 실패");
  }
  return res.json();
}

// 통합 이미지 업로드: 서버(Agent)가 인바디/음식 종류를 판단해 분기 처리
// 반환: { type: "inbody"|"food"|"unknown", ... }
export async function uploadImage(userId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE_URL}/image/upload?user_id=${userId}`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "업로드 실패");
  }
  return res.json();
}

// 영양성분 조회만 (기록 X) — foods: [{ name, quantity_g }]
export async function nutritionLookup(foods) {
  const res = await fetch(`${BASE_URL}/nutrition/lookup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ foods }),
  });
  if (!res.ok) throw new Error("영양성분 조회 실패");
  return res.json();
}

export async function getCalendar(userId, targetDate) {
  const res = await fetch(`${BASE_URL}/calendar/${targetDate}?user_id=${userId}`);
  return res.json();
}

export async function getCalendarMonth(userId, yearMonth) {
  const res = await fetch(`${BASE_URL}/calendar/month/${yearMonth}?user_id=${userId}`);
  return res.json();
}

export async function getWeeklyReport(userId) {
  const res = await fetch(`${BASE_URL}/report/weekly?user_id=${userId}`);
  return res.json();
}

export async function resumeChat(userId, threadId, message, onToken, onDone) {
  const response = await fetch(`${BASE_URL}/chat/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      thread_id: threadId,
      message,
    }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value);
    const lines = text.split("\n").filter((l) => l.startsWith("data: "));
    for (const line of lines) {
      try {
        const data = JSON.parse(line.replace("data: ", ""));
        if (data.type === "token") onToken(data.content);
        if (data.type === "done") onDone(data);
      } catch (e) {}
    }
  }
}
