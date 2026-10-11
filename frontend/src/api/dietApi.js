import { consumeEventStream } from "./eventStream";
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

function newStreamRunId() {
  return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function postEventStream(path, body, onToken, onDone, onProgress) {
  const streamRunId = newStreamRunId();
  let afterSeq = 0;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ ...body, stream_run_id: streamRunId, after_seq: afterSeq }),
      });
      await consumeEventStream(response, data => {
        if (data.type === "progress") onProgress?.(data);
        if (data.type === "token" || data.type === "answer_delta") onToken(data.content);
        if (data.type === "done" || data.type === "completed") onDone(data);
      }, { afterSeq });
      return;
    } catch (error) {
      afterSeq = error.lastSeq ?? afterSeq;
      const retryable = error instanceof TypeError || error.message.includes("완전히");
      if (attempt === 1 || !retryable) throw error;
    }
  }
}

export async function sendChatMessage(
  userId, message, onToken, onDone,
  pendingState = {}, messages = [], threadId = "default", mealType = null, onProgress = null
) {
  await postEventStream("/chat", {
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
    }, onToken, onDone, onProgress);
}

export async function getChatHistory(userId, threadId) {
  const res = await fetch(
    `${BASE_URL}/chat/history/${threadId}`,
    { headers: authHeaders() }
  );
  return res.json();
}

export async function getSessionRestore(threadId) {
  const res = await fetch(`${BASE_URL}/session/restore/${encodeURIComponent(threadId)}`, {
    headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  // A brand-new conversation has no durable checkpoint or chat rows yet.
  // Treat that expected 404 as an empty restore instead of a connection error.
  if (res.status === 404) {
    return {
      messages: [],
      pending_state: {},
      pending_proposal: null,
      interrupted: false,
    };
  }
  if (!res.ok) throw new Error(data.detail || "이전 상태를 불러오지 못했습니다.");
  return data;
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

export async function resumeChat(userId, threadId, message, onToken, onDone, decision = null, onProgress = null) {
  await postEventStream("/chat/resume", {
      thread_id: threadId,
      message,
      decision,
    }, onToken, onDone, onProgress);
}

export async function decideProposal(proposal, action) {
  const res = await fetch(`${BASE_URL}/proposals/decision`, {
    method: "POST", headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ proposal_id: proposal.id, version: proposal.version, action }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "제안 처리 실패");
  return data;
}

export async function reviseMeasurement(proposal, payload) {
  const res = await fetch(`${BASE_URL}/proposals/${proposal.id}/measurement`, {
    method: "PUT", headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ version: proposal.version, payload }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "측정값을 확인해주세요.");
  return data;
}

export async function deleteAccount() {
  const res = await fetch(`${BASE_URL}/users/me`, {
    method: "DELETE",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ confirmation: "DELETE" }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || {};
    const error = new Error(
      typeof detail === "string"
        ? detail
        : detail.message || "계정 삭제를 완료하지 못했습니다."
    );
    error.code = detail.code || "account_deletion_failed";
    error.retryable = Boolean(detail.retryable);
    error.status = res.status;
    throw error;
  }
  return data;
}
