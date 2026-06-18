import { useState } from "react";
import { supabase } from "../lib/supabaseClient";

export default function Auth() {
  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const handleSubmit = async () => {
    if (!email || !password) {
      setMessage("이메일과 비밀번호를 입력해주세요.");
      return;
    }
    setLoading(true);
    setMessage("");
    const { error } =
      mode === "login"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });
    if (error) {
      setMessage(error.message);
    } else if (mode === "signup") {
      setMessage("가입 확인 메일을 확인해주세요.");
    }
    setLoading(false);
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h2 style={styles.title}>🥗 MetaDiet AI</h2>
        <p style={styles.subtitle}>로그인하고 식단 코칭을 시작하세요</p>

        <div style={styles.tabRow}>
          {[
            { key: "login", label: "로그인" },
            { key: "signup", label: "회원가입" },
          ].map((t) => (
            <button
              key={t.key}
              style={{
                ...styles.tabBtn,
                ...(mode === t.key ? styles.tabBtnActive : {}),
              }}
              onClick={() => {
                setMode(t.key);
                setMessage("");
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div style={styles.section}>
          <label style={styles.label}>이메일</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            style={styles.input}
          />
        </div>

        <div style={styles.section}>
          <label style={styles.label}>비밀번호</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="********"
            style={styles.input}
          />
        </div>

        {message && <p style={styles.message}>{message}</p>}

        <button
          style={{ ...styles.submitBtn, opacity: loading ? 0.6 : 1 }}
          onClick={handleSubmit}
          disabled={loading}
        >
          {loading ? "처리 중..." : mode === "login" ? "로그인" : "가입하기"}
        </button>
      </div>
    </div>
  );
}

const styles = {
  container: { minHeight: "100vh", backgroundColor: "#f8f9fa", display: "flex", alignItems: "center", justifyContent: "center", padding: "20px" },
  card: { backgroundColor: "white", borderRadius: "16px", padding: "32px", width: "100%", maxWidth: "420px", boxShadow: "0 4px 20px rgba(0,0,0,0.08)" },
  title: { fontSize: "22px", fontWeight: "700", marginBottom: "8px", textAlign: "center" },
  subtitle: { fontSize: "14px", color: "#999", textAlign: "center", marginBottom: "24px" },
  tabRow: { display: "flex", gap: "8px", marginBottom: "20px" },
  tabBtn: { flex: 1, padding: "10px", borderRadius: "10px", border: "1.5px solid #e0e0e0", background: "white", cursor: "pointer", fontSize: "14px", fontWeight: "600", color: "#999" },
  tabBtnActive: { borderColor: "#4CAF50", background: "#f0faf0", color: "#333" },
  section: { marginBottom: "20px" },
  label: { display: "block", fontSize: "13px", fontWeight: "600", color: "#555", marginBottom: "8px" },
  input: { width: "100%", padding: "10px 14px", borderRadius: "10px", border: "1.5px solid #e0e0e0", fontSize: "16px", outline: "none", boxSizing: "border-box" },
  message: { fontSize: "13px", color: "#e05050", textAlign: "center", margin: "0 0 16px" },
  submitBtn: { width: "100%", padding: "14px", backgroundColor: "#4CAF50", color: "white", border: "none", borderRadius: "12px", fontSize: "16px", fontWeight: "600", cursor: "pointer" },
};
