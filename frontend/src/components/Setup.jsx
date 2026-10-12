import { useState, useEffect, useCallback, useRef } from "react";
import { getToken, BASE_URL, decideProposal, trackProductEvent } from "../api/dietApi";
import ProposalCard from './chat/ProposalCard';
import ActivityLevelSection from './setup/ActivityLevelSection';
import BodyMetricsSection from './setup/BodyMetricsSection';
import SetupSection from './setup/SetupSection';

export default function Setup({ onComplete }) {
  const [form, setForm] = useState({
    goal: "diet",
    region: "KR",
    height_cm: "",
    weight_kg: "",
    age: "",
    gender: "male",
    activity: "",
    general_adult_confirmed: false,
    target_weight_kg: "",
    target_date: "",
    goal_priority: "",
  });
  const [loading, setLoading] = useState(true);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const lookupRef = useRef(null);

  const loadExistingSetup = useCallback((isActive = () => true) => {
    lookupRef.current?.cancel();
    const controller = new AbortController();
    let cancelled = false;
    let timeoutId;
    const active = () => !cancelled && isActive();
    const timeout = new Promise((_, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error('서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.'));
        controller.abort();
      }, 90000);
    });
    lookupRef.current = { cancel: () => {
      cancelled = true;
      clearTimeout(timeoutId);
      controller.abort();
    }};
    setInitialLoading(true);
    setLoadError("");
    Promise.race([fetch(`${BASE_URL}/users/onboarding`,{signal:controller.signal,headers:{Authorization:`Bearer ${getToken()}`}})
      .then(async res=>{if(!res.ok) throw new Error('기존 설정 조회에 실패했습니다.'); return res.json();})
      , timeout])
      .then(data=>{if(active()){if(data.pending_proposal) setResult(data);
        else if(data.current_strategy) onComplete();}})
      .catch(e=>{if(active()) setLoadError(e.message || '기존 설정 조회에 실패했습니다.');})
      .finally(()=>{clearTimeout(timeoutId);if(active()){setInitialLoading(false);setLoading(false);}});
  },[onComplete]);

  useEffect(()=>{
    let active=true;
    loadExistingSetup(() => active);
    return ()=>{active=false;lookupRef.current?.cancel();};
  },[loadExistingSetup]);

  const handleSubmit = async () => {
    if (!form.height_cm || !form.weight_kg || !form.age || !form.activity || !form.general_adult_confirmed) {
      alert("모든 항목을 입력해주세요.");
      return;
    }
    setLoading(true);
    setError('');
    try {
      const body = {
        goal: form.goal,
        region: form.region,
        height_cm: Number(form.height_cm),
        weight_kg: Number(form.weight_kg),
        age: Number(form.age),
        sex: form.gender, activity: form.activity,
        general_adult_confirmed: form.general_adult_confirmed,
      };
      // 장기 목표 3개는 선택 입력 — 값이 있을 때만 전송(빈 문자열이면 백엔드 float 파싱 실패)
      if (form.target_weight_kg) body.target_weight_kg=Number(form.target_weight_kg);
      if (form.target_date) body.target_date=form.target_date;
      if (form.goal_priority) body.goal_priority=form.goal_priority;
      const res = await fetch(`${BASE_URL}/users/onboarding`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}`, 'Content-Type':'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if(!res.ok) throw new Error(typeof data.detail==='string'?data.detail:'입력값과 적용대상을 확인해주세요.');
      setResult(data);
    } catch (e) {
      setError(e.message || '초기 제안 생성에 실패했습니다. 다시 시도해주세요.');
    }
    setLoading(false);
  };

  const handleDecision=async action=>{
    setLoading(true); setError('');
    try {
      const decision=await decideProposal(result.pending_proposal,action);
      if(action==='confirm' && decision.status==='confirmed') {
        trackProductEvent("onboarding_completed");
        onComplete();
      }
      else if(action==='cancel' && result.current_strategy) onComplete();
      else if(action==='cancel') setResult(null);
      else throw new Error('확정 상태를 확인하지 못했습니다. 다시 시도해주세요.');
    }catch(e){setError(e.message);}
    finally{setLoading(false);}
  };

  const GOAL_LABELS = {
    diet: { label: "다이어트 🔥", desc: "체지방 감소" },
    bulk: { label: "증량 💪", desc: "근육량 증가" },
    maintain: { label: "유지 ⚖️", desc: "현재 체형 유지" },
  };

  if (initialLoading) return <div style={styles.container}><div style={styles.card} role="status">
    <h2 style={styles.title}>기존 설정을 확인하는 중입니다.</h2>
    <p style={styles.subtitle}>저장된 설정을 불러오고 있어요. 무료 서버가 쉬고 있었다면 기동에 약 1분이 걸릴 수 있습니다. 90초 안에 응답이 없으면 다시 시도할 수 있어요.</p>
  </div></div>;

  if (loadError) return <div style={styles.container}><div style={styles.card}>
    <h2 style={styles.title}>설정을 불러오지 못했습니다.</h2>
    <p role="alert">{loadError}</p>
    <button style={styles.submitBtn} onClick={() => loadExistingSetup()}>다시 시도</button>
  </div></div>;

  if(result?.pending_proposal) return <div style={styles.container}><div style={styles.card}>
    <h2 style={styles.title}>초기 전략 제안</h2>
    <p>{result.message}</p>
    {result.current_strategy && <p>확정 전에는 기존 전략이 유지됩니다.</p>}
    {error && <p role="alert">{error}</p>}
    <ProposalCard proposal={result.pending_proposal} busy={loading} onDecision={handleDecision}/>
    <button disabled={loading} onClick={()=>{setResult(null);setError('');}}>입력을 수정해 다시 제안</button>
    {result.current_strategy && <button disabled={loading} onClick={()=>handleDecision('cancel')}>기존 전략으로 계속</button>}
  </div></div>;

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
        {error && <p role="alert">{error}</p>}

        <SetupSection title="목표와 기준" description="식단 전략 계산에 사용할 기본 기준을 선택해요." required>
          <div className="setup-subsection">
            <span className="setup-subsection__label">목표</span>
            <div style={styles.goalGrid}>
              {Object.entries(GOAL_LABELS).map(([key, val]) => (
                <button
                  key={key}
                  style={{ ...styles.goalBtn, ...(form.goal === key ? styles.goalBtnActive : {}) }}
                  onClick={() => setForm({ ...form, goal: key })}
                >
                  <span style={styles.goalLabel}>{val.label}</span>
                  <span style={styles.goalDesc}>{val.desc}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="setup-subsection">
            <span className="setup-subsection__label">영양 기준 지역</span>
            <div style={styles.genderRow}>
              <button style={{ ...styles.genderBtn, ...styles.genderBtnActive }}>한국 🇰🇷 (KDRIs 기준)</button>
            </div>
          </div>
          <div className="setup-subsection">
            <span className="setup-subsection__label">성별</span>
            <div style={styles.genderRow}>
              {["male", "female"].map((g) => (
                <button
                  key={g}
                  style={{ ...styles.genderBtn, ...(form.gender === g ? styles.genderBtnActive : {}) }}
                  onClick={() => setForm({ ...form, gender: g })}
                >
                  {g === "male" ? "남성" : "여성"}
                </button>
              ))}
            </div>
          </div>
        </SetupSection>

        <BodyMetricsSection
          values={form}
          onChange={(field, value) => setForm({ ...form, [field]: value })}
        />

        <ActivityLevelSection
          value={form.activity}
          confirmed={form.general_adult_confirmed}
          onActivityChange={(activity) => setForm({ ...form, activity })}
          onConfirmationChange={(general_adult_confirmed) =>
            setForm({ ...form, general_adult_confirmed })
          }
        />
        <SetupSection title="장기 목표" description="원하면 목표 체중과 기간, 우선순위를 추가할 수 있어요." optional>
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
        </SetupSection>

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
  container: { minHeight: "100vh", background:"radial-gradient(circle at 50% -20%, #e8f4ee 0, #f6f9f7 42%, #f6f9f7 100%)", display: "flex", alignItems: "center", justifyContent: "center", padding: "20px" },
  card: { backgroundColor: "rgba(255,255,255,.95)", border:"1px solid #dde8e2", borderRadius: "24px", padding: "32px", width: "100%", maxWidth: "460px", boxShadow: "0 18px 50px rgba(26,67,51,.1)" },
  title: { fontFamily:"Georgia, 'Times New Roman', serif", color:"#22332d", fontSize: "26px", fontWeight: "600", marginBottom: "8px", textAlign: "center" },
  subtitle: { fontSize: "14px", color: "#6a7a73", textAlign: "center", marginBottom: "24px" },
  section: { marginBottom: "20px" },
  label: { display: "block", fontSize: "13px", fontWeight: "600", color: "#555", marginBottom: "8px" },
  goalGrid: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px" },
  goalBtn: { padding: "12px 8px", borderRadius: "10px", borderWidth: "1.5px", borderStyle: "solid", borderColor: "#e0e0e0", background: "white", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" },
  goalBtnActive: { borderColor: "#1f7a58", background: "#f0f7f3" },
  goalLabel: { fontSize: "13px", fontWeight: "600" },
  goalDesc: { fontSize: "11px", color: "#999" },
  genderRow: { display: "flex", gap: "8px" },
  genderBtn: { flex: 1, padding: "10px", borderRadius: "10px", borderWidth: "1.5px", borderStyle: "solid", borderColor: "#e0e0e0", background: "white", cursor: "pointer", fontSize: "14px" },
  genderBtnActive: { borderColor: "#1f7a58", background: "#f0f7f3", fontWeight: "600" },
  inputRow: { display: "flex", alignItems: "center", gap: "8px" },
  input: { flex: 1, padding: "10px 14px", borderRadius: "10px", border: "1.5px solid #e0e0e0", fontSize: "16px", outline: "none" },
  unit: { fontSize: "14px", color: "#999", width: "24px" },
  submitBtn: { width: "100%", padding: "14px", backgroundColor: "#1f7a58", color: "white", border: "none", borderRadius: "12px", fontSize: "16px", fontWeight: "700", cursor: "pointer", marginTop: "8px" },
  successIcon: { fontSize: "40px", textAlign: "center", marginBottom: "12px" },
  strategyGrid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", margin: "20px 0" },
  strategyItem: { backgroundColor: "#f8f9fa", borderRadius: "10px", padding: "12px 8px", textAlign: "center", display: "flex", flexDirection: "column" },
  strategyLabel: { fontSize: "11px", color: "#999", marginBottom: "4px" },
  strategyValue: { fontSize: "20px", fontWeight: "700", color: "#1f7a58" },
  strategyUnit: { fontSize: "11px", color: "#999" },
  note: { fontSize: "13px", color: "#666", textAlign: "center", margin: "16px 0" },
  startBtn: { width: "100%", padding: "14px", backgroundColor: "#1f7a58", color: "white", border: "none", borderRadius: "12px", fontSize: "16px", fontWeight: "700", cursor: "pointer" },
};
