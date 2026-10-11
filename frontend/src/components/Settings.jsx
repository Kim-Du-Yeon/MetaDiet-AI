import { useState } from "react";
import { deleteAccount, setToken } from "../api/dietApi";
import { supabase } from "../lib/supabaseClient";

export function clearLocalSupabaseSession(storage = window.localStorage) {
  const keys = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith("sb-") && key.endsWith("-auth-token")) keys.push(key);
  }
  keys.forEach((key) => storage.removeItem(key));
}

export default function Settings({ session, onDeleted }) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [authDeletionPending, setAuthDeletionPending] = useState(false);
  const provider = session?.user?.app_metadata?.provider;
  const supportsPasswordReauth = Boolean(session?.user?.email) && (!provider || provider === "email");

  const finishDeletion = async () => {
    clearLocalSupabaseSession();
    setToken(null);
    onDeleted();
  };

  const requestDeletion = async () => {
    try {
      await deleteAccount();
      await finishDeletion();
    } catch (error) {
      if (error.code === "auth_deletion_pending") {
        setAuthDeletionPending(true);
        setMessage("서비스 데이터는 삭제됐지만 인증 계정 삭제를 재시도해야 합니다.");
        return;
      }
      if (error.code === "recent_authentication_required") {
        setAuthDeletionPending(false);
        setPassword("");
        setMessage("세션 확인 시간이 지났습니다. 비밀번호를 다시 입력해주세요.");
        return;
      }
      setMessage(error.message || "계정 삭제를 완료하지 못했습니다.");
    }
  };

  const handleDelete = async () => {
    if (!password || confirmation !== "DELETE") {
      setMessage("비밀번호와 DELETE 확인값을 입력해주세요.");
      return;
    }
    if (!supportsPasswordReauth) {
      setMessage("현재 로그인 방식의 재인증은 아직 지원하지 않습니다.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: session.user.email,
        password,
      });
      if (error || !data?.session?.access_token) {
        setMessage("비밀번호가 올바른지 확인해주세요.");
        return;
      }
      setToken(data.session.access_token);
      setPassword("");
      await requestDeletion();
    } finally {
      setLoading(false);
    }
  };

  const retryAuthDeletion = async () => {
    setLoading(true);
    setMessage("");
    try {
      await requestDeletion();
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="settings-page">
      <section className="settings-card">
        <p className="settings-eyebrow">ACCOUNT</p>
        <h1>계정 설정</h1>
        <p className="settings-email">{session?.user?.email}</p>
      </section>

      <section className="settings-card settings-danger" aria-labelledby="delete-account-title">
        <p className="settings-eyebrow settings-eyebrow--danger">DANGER ZONE</p>
        <h2 id="delete-account-title">계정과 모든 기록 삭제</h2>
        <p>
          식사·인바디·전략·대화 기록과 진행 중인 제안이 영구 삭제됩니다.
          이 작업은 되돌릴 수 없습니다.
        </p>

        {!supportsPasswordReauth && (
          <p className="settings-notice" role="status">
            현재 로그인 방식의 재인증은 아직 지원하지 않습니다.
          </p>
        )}

        <label className="settings-label" htmlFor="delete-password">현재 비밀번호</label>
        <input
          id="delete-password"
          className="settings-input"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          disabled={!supportsPasswordReauth || loading || authDeletionPending}
        />

        <label className="settings-label" htmlFor="delete-confirmation">삭제 확인</label>
        <input
          id="delete-confirmation"
          className="settings-input"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          placeholder="DELETE 입력"
          disabled={!supportsPasswordReauth || loading || authDeletionPending}
        />

        {message && <p className="settings-message" role="status">{message}</p>}

        {authDeletionPending ? (
          <button className="settings-delete-button" onClick={retryAuthDeletion} disabled={loading}>
            {loading ? "재시도 중..." : "인증 계정 삭제 재시도"}
          </button>
        ) : (
          <button
            className="settings-delete-button"
            onClick={handleDelete}
            disabled={!supportsPasswordReauth || loading}
          >
            {loading ? "삭제 중..." : "계정 영구 삭제"}
          </button>
        )}
      </section>
    </main>
  );
}
