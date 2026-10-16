export function reportRequestTiming(ids, stage, started, extra = {}) {
  const row = { request_id: ids.requestId, attempt_id: ids.attemptId,
    stage, elapsed_ms: Math.round((performance.now() - started) * 1000) / 1000,
    visibility: document.visibilityState, ...extra };
  // Fixed labels and durations only: no request body, token, user ID, or answer.
  window.dispatchEvent(new CustomEvent('metadiet:request-timing', { detail: row }));
  console.info('[request_timing]', JSON.stringify(row));
}
