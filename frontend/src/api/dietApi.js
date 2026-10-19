import { consumeEventStream } from "./eventStream";
import { reportRequestTiming } from './requestTiming';
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

export async function proposeNutritionLabel(payload) {
  const response = notifyAuthExpired(await fetch(`${BASE_URL}/nutrition/label-proposal`, {
    method: "POST", headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  }));
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "기준량·영양값·날짜를 확인해주세요.");
  return data;
}
function notifyAuthExpired(response) {
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("metadiet:auth-expired"));
  }
  return response;
}
function authHeaders(extra = {}) {
  return _token ? { ...extra, Authorization: `Bearer ${_token}` } : extra;
}

function analyticsUuid() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const value = Math.floor(Math.random() * 16);
    return (character === "x" ? value : (value & 0x3) | 0x8).toString(16);
  });
}

function analyticsSessionId() {
  const key = "metadiet:analytics-session";
  let value = window.sessionStorage.getItem(key);
  if (!value) {
    value = analyticsUuid();
    window.sessionStorage.setItem(key, value);
  }
  return value;
}

export async function recordProductEvent(eventName, options = {}) {
  const payload = {
    event_name: eventName,
    status: options.status || "success",
    client_event_id: options.clientEventId || analyticsUuid(),
    session_id: analyticsSessionId(),
    duration_ms: options.durationMs == null ? null : Math.max(0, Math.round(options.durationMs)),
    trace_id: options.traceId || null,
    properties: options.properties || {},
  };
  const res = notifyAuthExpired(await fetch(`${BASE_URL}/analytics/events`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  }));
  if (!res.ok) throw new Error("제품 사용 지표를 기록하지 못했습니다.");
  return res.json();
}

// 분석 장애가 사용자 작업을 막지 않도록 호출부에서 await 없이 사용한다.
export function trackProductEvent(eventName, options = {}) {
  void recordProductEvent(eventName, options).catch(() => {});
}

export async function getAdminAnalytics(days = 7) {
  const res = notifyAuthExpired(await fetch(`${BASE_URL}/admin/analytics/overview?days=${days}`, {
    headers: authHeaders(),
  }));
  if (res.status === 403) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "운영 지표를 불러오지 못했습니다.");
  return data;
}

async function adminFeedbackRequest(path, options = {}) {
  const res = notifyAuthExpired(await fetch(`${BASE_URL}/admin/feedback${path}`, {
    ...options, cache: 'no-store', headers: authHeaders({'Content-Type':'application/json'}),
  }));
  if (res.status === 403 && !options.method) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : '피드백을 처리하지 못했습니다. 다시 시도해주세요.');
    error.status = res.status;
    throw error;
  }
  return data;
}

export function getAdminFeedback({status = '', category = '', assignee = '', offset = 0} = {}) {
  const query = new URLSearchParams({limit:'20', offset:String(offset)});
  if (status) query.set('status', status);
  if (category) query.set('category', category);
  if (assignee) query.set('assignee', assignee);
  return adminFeedbackRequest(`?${query}`);
}
export function getAdminFeedbackDetail(id) {
  return adminFeedbackRequest(`/${encodeURIComponent(id)}`);
}
export function getAdminFeedbackAssignees() {
  return adminFeedbackRequest('/assignees');
}
export function getAdminFeedbackHistory(id, beforeVersion = null) {
  const query = beforeVersion ? `?before_version=${beforeVersion}` : '';
  return adminFeedbackRequest(`/${encodeURIComponent(id)}/history${query}`);
}
export function updateAdminFeedback(id, payload) {
  return adminFeedbackRequest(`/${encodeURIComponent(id)}`, {method:'PATCH', body:JSON.stringify(payload)});
}

function newStreamRunId() {
  return analyticsUuid();
}

async function postEventStream(path, body, onToken, onDone, onProgress) {
  const streamRunId = newStreamRunId();
  const started = performance.now();
  const progressTiming = {firstSeen:false};
  onProgress?.({phase:'request_wait', label:'상담 요청을 처리하고 있어요. 서버 응답을 기다리는 중입니다.',
    requestId:streamRunId, requestStartedAt:started, receivedAt:started, local:true});
  let afterSeq = 0;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const attemptId = analyticsUuid();
    const ids = {requestId:streamRunId, attemptId};
    reportRequestTiming(ids, 'fetch_start', started);
    try {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json", 'X-Request-ID':streamRunId, 'X-Attempt-ID':attemptId }),
        body: JSON.stringify({ ...body, stream_run_id: streamRunId, after_seq: afterSeq,
          ...(path === '/chat' ? { stream_protocol: 2, stream_reconnect: attempt > 0 } : {}) }),
      });
      reportRequestTiming(ids, 'response_headers', started, {status:response.status});
      await consumeEventStream(response, data => {
        if (data.type === "progress") {
          if (!progressTiming.firstSeen) { progressTiming.firstSeen = true; reportRequestTiming(ids, 'first_server_progress', started); }
          onProgress?.({...data, requestId:streamRunId, attemptId, requestStartedAt:started, receivedAt:performance.now()});
        }
        if (data.type === "token" || data.type === "answer_delta") onToken(data.content);
        if (data.type === "done" || data.type === "completed") { reportRequestTiming(ids, 'completed', started); onDone(data); }
      }, { afterSeq });
      return;
    } catch (error) {
      reportRequestTiming(ids, 'attempt_failed', started, {error_type:error.name});
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
  const res = notifyAuthExpired(await fetch(`${BASE_URL}/session/restore/${encodeURIComponent(threadId)}`, {
    headers: authHeaders(),
  }));
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

export async function getDashboardSummary() {
  const res = notifyAuthExpired(await fetch(`${BASE_URL}/dashboard/summary`, { headers: authHeaders() }));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "측정 기록을 불러오지 못했습니다.");
  return data;
}

export async function proposeWeight(payload) {
  return postJson("/measurements/weight", payload, "체중 기록 제안을 만들지 못했습니다.");
}

export async function proposeBodyComposition(payload) {
  return postJson("/measurements/body-composition", payload, "체성분 기록 제안을 만들지 못했습니다.");
}

async function postJson(path, payload, fallback) {
  const res = notifyAuthExpired(await fetch(`${BASE_URL}${path}`, {
    method: "POST", headers: authHeaders({ "Content-Type": "application/json" }), body: JSON.stringify(payload),
  }));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : fallback);
  return data;
}

export async function getCurrentStrategy() {
  const res = await fetch(`${BASE_URL}/strategy/current`, { headers: authHeaders() });
  return res.json();
}

export async function getCaloriesHistory() {
  const res = await fetch(`${BASE_URL}/calories/history`, { headers: authHeaders() });
  return res.json();
}

export async function updateMeal(mealId, quantityG, options = {}) {
  const res = notifyAuthExpired(await fetch(`${BASE_URL}/meal/update`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ meal_id: mealId, quantity_g: quantityG,
      ...(options.selectedDate ? {include_snapshot:true, selected_date:options.selectedDate,
        thread_id:options.threadId || null, expected_record_version:options.recordVersion || null} : {}) }),
  }));
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '기록 수정에 실패했습니다.');
  return data;
}

export async function deleteMeal(mealId, options = {}) {
  const query = new URLSearchParams();
  if (options.selectedDate) {
    query.set('include_snapshot','true'); query.set('selected_date',options.selectedDate);
    if (options.threadId) query.set('thread_id',options.threadId);
    if (options.recordVersion) query.set('expected_record_version',options.recordVersion);
  }
  const res = notifyAuthExpired(await fetch(`${BASE_URL}/meal/delete/${mealId}${query.size ? '?'+query : ''}`, {
    method: "DELETE",
    headers: authHeaders(),
  }));
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '기록 삭제에 실패했습니다.');
  return data;
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
  const kind = proposal.kind === "weight" ? "weight" : "measurement";
  const res = await fetch(`${BASE_URL}/proposals/${proposal.id}/${kind}`, {
    method: "PUT", headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ version: proposal.version, payload }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "측정값을 확인해주세요.");
  return data;
}

export async function reviseMeal(proposal, payload) {
  const res = await fetch(`${BASE_URL}/proposals/${proposal.id}/meal`, {
    method: 'PUT', headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ version: proposal.version, ...payload }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '분량을 확인해주세요.');
  return data;
}

export async function resolveMealChoices(payload) {
  const res = await fetch(`${BASE_URL}/nutrition/meal-choices`, {
    method:'POST', headers:authHeaders({'Content-Type':'application/json'}), body:JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '선택 또는 입력값을 확인해주세요.');
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

export async function submitBetaFeedback(payload) {
  const res = notifyAuthExpired(await fetch(`${BASE_URL}/feedback`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  }));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const error = new Error(
      typeof data.detail === "string"
        ? data.detail
        : "피드백을 전송하지 못했습니다. 잠시 후 다시 시도해주세요."
    );
    error.status = res.status;
    error.retryable = res.status >= 500 || res.status === 429;
    throw error;
  }
  return data;
}
