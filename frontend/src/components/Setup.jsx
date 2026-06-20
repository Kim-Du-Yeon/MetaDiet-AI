import { useState } from "react";
import { getToken } from "../api/dietApi";

export default function Setup({ onComplete }) {
  const [form, setForm] = useState({
    goal: "diet",
    region: "KR",
    height_cm: "",
    weight_kg: "",
    age: "",
    gender: "male",
    target_weight_kg: "",
    target_date: "",
    goal_priority: "",
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleSubmit = async () => {
    if (!form.height_cm || !form.weight_kg || !form.age) {
      alert("모든 항목을 입력해주세요.");
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({
        goal: form.goal,
        region: form.region,
        height_cm: form.height_cm,
        weight_kg: form.weight_kg,
        age: form.age,
        gender: form.gender,
      });
      // 장기 목표 3개는 선택 입력 — 값이 있을 때만 전송(빈 문자열이면 백엔드 float 파싱 실패)
      if (form.target_weight_kg) params.set("target_weight_kg", form.target_weight_kg);
      if (form.target_date) params.set("target_date", form.target_date);
      if (form.goal_priority) params.set("goal_priority", form.goal_priority);
      const res = await fetch(`http://localhost:8000/users/setup?${params}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      alert("오류가 발생했습니다.");
    }
    setLoading(false);
  };

  const GOAL_LABELS = {
    diet: { label: "다이어트 🔥", desc: "체지방 감소" },
    bulk: { label: "증량 💪", desc: "근육량 증가" },
    maintain: { label: "유지 ⚖️", desc: "현재 체형 유지" },
  };

  if (result) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={styles.successIcon}>✅</div>
          <h2 style={styles.title}>초기 전략이 설정됐습니다!</h2>
          <div style={styles.strategyGrid}>
            <div style={styles.strategyItem}>
              <span style={styles.strategyLabel}>하루 칼로리</span>
              <span style={styles.strategyValue}>{result.daily_calories}</span>
              <span style={styles.strategyUnit}>kcal</span>
            </div>
            <div style={styles.strategyItem}>
              <span style={styles.strategyLabel}>단백질</span>
              <span style={styles.strategyValue}>{result.protein_g}</span>
              <span style={styles.strategyUnit}>g</span>
            </div>
            <div style={styles.strategyItem}>
              <span style={styles.strategyLabel}>탄수화물</span>
              <span style={styles.strategyValue}>{result.carbs_g}</span>
              <span style={styles.strategyUnit}>g</span>
            </div>
            <div style={styles.strategyItem}>
              <span style={styles.strategyLabel}>지방</span>
              <span style={styles.strategyValue}>{result.fat_g}</span>
              <span style={styles.strategyUnit}>g</span>
            </div>
          </div>
          <p style={styles.note}>{result.strategy_note}</p>
          <button style={styles.startBtn} onClick={onComplete}>
            시작하기 →
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h2 style={styles.title}>🥗 식단 목표 설정</h2>
        <p style={styles.subtitle}>정확한 전략을 위해 기본 정보를 입력해주세요</p>

        {/* 목표 선택 */}
        <div style={styles.section}>
          <label style={styles.label}>목표</label>
          <div style={styles.goalGrid}>
            {Object.entries(GOAL_LABELS).map(([key, val]) => (
              <button
                key={key}
                style={{
                  ...styles.goalBtn,
                  ...(form.goal === key ? styles.goalBtnActive : {}),
                }}
                onClick={() => setForm({ ...form, goal: key })}
              >
                <span style={styles.goalLabel}>{val.label}</span>
                <span style={styles.goalDesc}>{val.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* 영양 기준 지역 */}
        <div style={styles.section}>
          <label style={styles.label}>영양 기준 지역</label>
          <div style={styles.genderRow}>
            {[
              { key: "KR", label: "한국 🇰🇷 (KDRIs 기준)" },
              { key: "INTL", label: "국제 🌍 (WHO 기준)" },
            ].map((r) => (
              <button
                key={r.key}
                style={{
                  ...styles.genderBtn,
                  ...(form.region === r.key ? styles.genderBtnActive : {}),
                }}
                onClick={() => setForm({ ...form, region: r.key })}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        {/* 성별 */}
        <div style={styles.section}>
          <label style={styles.label}>성별</label>
          <div style={styles.genderRow}>
            {["male", "female"].map((g) => (
              <button
                key={g}
                style={{
                  ...styles.genderBtn,
                  ...(form.gender === g ? styles.genderBtnActive : {}),
                }}
                onClick={() => setForm({ ...form, gender: g })}
              >
                {g === "male" ? "남성" : "여성"}
              </button>
            ))}
          </div>
        </div>

        {/* 신체 정보 */}
        {[
          { key: "age", label: "나이", unit: "세", placeholder: "25" },
          { key: "height_cm", label: "키", unit: "cm", placeholder: "175" },
          { key: "weight_kg", label: "체중", unit: "kg", placeholder: "70" },
        ].map((field) => (
          <div key={field.key} style={styles.section}>
            <label style={styles.label}>{field.label}</label>
            <div style={styles.inputRow}>
              <input
                type="number"
                value={form[field.key]}
                onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
                placeholder={field.placeholder}
                style={styles.input}
              />
              <span style={styles.unit}>{field.unit}</span>
            </div>
          </div>
        ))}

        {/* 장기 목표 (선택) */}
        <div style={styles.section}>
          <label style={styles.label}>장기 목표 (선택)</label>
          <div style={styles.inputRow}>
            <input
              type="number"
              value={form.target_weight_kg}
              onChange={(e) => setForm({ ...form, target_weight_kg: e.target.value })}
              placeholder="목표 체중"
              style={styles.input}
            />
            <span style={styles.unit}>kg</span>
          </div>
          <input
            type="date"
            value={form.target_date}
            onChange={(e) => setForm({ ...form, target_date: e.target.value })}
            style={{ ...styles.input, width: "100%", marginTop: "8px", boxSizing: "border-box" }}
          />
          <div style={{ ...styles.genderRow, marginTop: "8px" }}>
            {[
              { key: "speed", label: "감량속도 우선" },
              { key: "muscle", label: "근육유지 우선" },
              { key: "balance", label: "균형" },
            ].map((p) => (
              <button
                key={p.key}
                style={{
                  ...styles.genderBtn,
                  ...(form.goal_priority === p.key ? styles.genderBtnActive : {}),
                }}
                onClick={() =>
                  setForm({ ...form, goal_priority: form.goal_priority === p.key ? "" : p.key })
                }
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <button
          style={{ ...styles.submitBtn, opacity: loading ? 0.6 : 1 }}
          onClick={handleSubmit}
          disabled={loading}
        >
          {loading ? "전략 계산 중..." : "전략 설정하기"}
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
  section: { marginBottom: "20px" },
  label: { display: "block", fontSize: "13px", fontWeight: "600", color: "#555", marginBottom: "8px" },
  goalGrid: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px" },
  goalBtn: { padding: "12px 8px", borderRadius: "10px", border: "1.5px solid #e0e0e0", background: "white", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" },
  goalBtnActive: { borderColor: "#4CAF50", background: "#f0faf0" },
  goalLabel: { fontSize: "13px", fontWeight: "600" },
  goalDesc: { fontSize: "11px", color: "#999" },
  genderRow: { display: "flex", gap: "8px" },
  genderBtn: { flex: 1, padding: "10px", borderRadius: "10px", border: "1.5px solid #e0e0e0", background: "white", cursor: "pointer", fontSize: "14px" },
  genderBtnActive: { borderColor: "#4CAF50", background: "#f0faf0", fontWeight: "600" },
  inputRow: { display: "flex", alignItems: "center", gap: "8px" },
  input: { flex: 1, padding: "10px 14px", borderRadius: "10px", border: "1.5px solid #e0e0e0", fontSize: "16px", outline: "none" },
  unit: { fontSize: "14px", color: "#999", width: "24px" },
  submitBtn: { width: "100%", padding: "14px", backgroundColor: "#4CAF50", color: "white", border: "none", borderRadius: "12px", fontSize: "16px", fontWeight: "600", cursor: "pointer", marginTop: "8px" },
  successIcon: { fontSize: "40px", textAlign: "center", marginBottom: "12px" },
  strategyGrid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", margin: "20px 0" },
  strategyItem: { backgroundColor: "#f8f9fa", borderRadius: "10px", padding: "12px 8px", textAlign: "center", display: "flex", flexDirection: "column" },
  strategyLabel: { fontSize: "11px", color: "#999", marginBottom: "4px" },
  strategyValue: { fontSize: "20px", fontWeight: "700", color: "#4CAF50" },
  strategyUnit: { fontSize: "11px", color: "#999" },
  note: { fontSize: "13px", color: "#666", textAlign: "center", margin: "16px 0" },
  startBtn: { width: "100%", padding: "14px", backgroundColor: "#4CAF50", color: "white", border: "none", borderRadius: "12px", fontSize: "16px", fontWeight: "600", cursor: "pointer" },
};