import { useState } from "react";
import { supabase } from "../lib/supabaseClient";
import LegalNotices from "./LegalNotices";
import "./Auth.css";

export default function Auth() {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const handleSubmit = async (event) => {
    event?.preventDefault();
    if (!email || !password) {
      setMessage("이메일과 비밀번호를 입력해주세요.");
      return;
    }
    setLoading(true);
    setMessage("");
    const { error } = mode === "login"
      ? await supabase.auth.signInWithPassword({ email, password })
      : await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: window.location.origin },
      });
    if (error) setMessage(error.message);
    else if (mode === "signup") setMessage("가입 확인 메일을 확인해주세요.");
    setLoading(false);
  };

  const selectMode = (nextMode) => {
    setMode(nextMode);
    setMessage("");
  };

  return <main className="auth-page">
    <form className="auth-card" aria-label={mode === "login" ? "계정 로그인" : "계정 만들기"} onSubmit={handleSubmit}>
      <header className="auth-header">
        <span className="auth-eyebrow">MetaDiet AI</span>
        <h1>{mode === "login" ? "다시 만나서 반가워요" : "식단 코칭 시작하기"}</h1>
        <p>내 기록과 검토된 영양 근거를 바탕으로 계획을 관리합니다.</p>
      </header>
      <div className="auth-tabs" role="tablist" aria-label="계정 방식">
        <button type="button" role="tab" aria-selected={mode === "login"} onClick={() => selectMode("login")}>로그인</button>
        <button type="button" role="tab" aria-selected={mode === "signup"} onClick={() => selectMode("signup")}>회원가입</button>
      </div>
      <label className="auth-field" htmlFor="auth-email"><span>이메일</span>
        <input id="auth-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" />
      </label>
      <label className="auth-field" htmlFor="auth-password"><span>비밀번호</span>
        <input id="auth-password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="8자 이상 입력" />
      </label>
      {message && <p className="auth-message" role="alert">{message}</p>}
      <button className="auth-submit" type="submit" disabled={loading}>{loading ? "처리 중…" : mode === "login" ? "로그인" : "가입하기"}</button>
    </form>
    <LegalNotices />
  </main>;
}
