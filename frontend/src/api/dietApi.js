export const BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8080";

// 인증은 Authorization 헤더(Supabase JWT)가 담당한다. 아래 함수들의 `userId`
// 매개변수는 백엔드가 user_id를 더 이상 받지 않게 된 뒤로는 사용되지 않지만,
// 기존 호출부(ChatInterface/CalendarView 등) 시그니처를 깨지 않기 위해 유지한다.
let _token = null;
export function setToken(token) {
  _token = token;
}
export function getToken() {
  return _token;
}
function authHeaders(extra = {}) {
  return _token ? { ...extra, Authorization: `Bearer ${_token}` } : extra;
}

export async function sendChatMessage(
  userId, message, onToken, onDone,
  pendingState = {}, messages = [], threadId = "default", mealType = null
) {
  const response = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      message,
      thread_id: threadId,
      pending_meals: null,
      awaiting_confirmation: false,
      plan_date: null,
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
    `${BASE_URL}/chat/history/${threadId}`,
    { headers: authHeaders() }
  );
  return res.json();
}

export async function rollbackToCheckpoint(userId, threadId, checkpointId) {
  const res = await fetch(
    `${BASE_URL}/chat/rollback?thread_id=${threadId}&checkpoint_id=${checkpointId}`,
    { method: "POST", headers: authHeaders() }
  );
  return res.json();
}

export async function uploadInbody(userId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE_URL}/inbody/upload`, {
    method: "POST",
    headers: authHeaders(),
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
  const res = await fetch(`${BASE_URL}/image/upload`, {
    method: "POST",
    headers: authHeaders(),
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

export async function getCalendar(targetDate) {
  const res = await fetch(`${BASE_URL}/calendar/${targetDate}`, { headers: authHeaders() });
  return res.json();
}

export async function getCalendarMonth(yearMonth) {
  const res = await fetch(`${BASE_URL}/calendar/month/${yearMonth}`, { headers: authHeaders() });
  return res.json();
}

export async function getWeeklyReport(userId) {
  const res = await fetch(`${BASE_URL}/report/weekly`, { headers: authHeaders() });
  return res.json();
}

export async function getInbodyHistory() {
  const res = await fetch(`${BASE_URL}/inbody/history`, { headers: authHeaders() });
  return res.json();
}

export async function getCurrentStrategy() {
  const res = await fetch(`${BASE_URL}/strategy/current`, { headers: authHeaders() });
  return res.json();
}

export async function getCaloriesHistory() {
  const res = await fetch(`${BASE_URL}/calories/history`, { headers: authHeaders() });
  return res.json();
}

export async function updateMeal(mealId, quantityG) {
  const res = await fetch(`${BASE_URL}/meal/update`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ meal_id: mealId, quantity_g: quantityG }),
  });
  return res.json();
}

export async function deleteMeal(mealId) {
  const res = await fetch(`${BASE_URL}/meal/delete/${mealId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return res.json();
}

export async function resumeChat(userId, threadId, message, onToken, onDone) {
  const response = await fetch(`${BASE_URL}/chat/resume`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
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
