import { useState, useEffect } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer
} from "recharts";
import { getCalendar, getDashboardSummary, getCurrentStrategy, getCaloriesHistory, proposeWeight,
  proposeBodyComposition, uploadInbody, decideProposal, reviseMeasurement } from "../../api/dietApi";
import ProposalCard from "../chat/ProposalCard";

export default function Dashboard() {
  const [inbodyData, setInbodyData] = useState([]);
  const [strategy, setStrategy] = useState(null);
  const [todayNutrition, setTodayNutrition] = useState(null);
  const [calorieHistory, setCalorieHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [entryMode, setEntryMode] = useState(null);
  const [approval, setApproval] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ measured_date: new Date().toISOString().slice(0, 10), weight_kg: "", skeletal_muscle_kg: "", body_fat_pct: "" });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const today = new Date().toISOString().split("T")[0];
      const [summary, strat, todayData, calorieData] = await Promise.all([
        getDashboardSummary(),
        getCurrentStrategy(),
        getCalendar(today),
        getCaloriesHistory(),
      ]);
      setInbodyData(summary);
      setStrategy(strat);
      setTodayNutrition(todayData.total || {});
      setCalorieHistory(calorieData.days || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  if (loading) return <div style={styles.loading}>로딩 중...</div>;

  const weightHistory = inbodyData.weight_history || [];
  const compositionHistory = inbodyData.body_composition_history || [];
  const latestWeight = inbodyData.latest_weight;
  const latestInbody = inbodyData.latest_body_composition;
  const firstWeight = weightHistory[0];
  const firstInbody = compositionHistory[0];
  const weightChange = latestWeight && firstWeight
    ? (latestWeight.weight_kg - firstWeight.weight_kg).toFixed(1) : null;
  const muscleChange = latestInbody && firstInbody
    ? (latestInbody.skeletal_muscle_kg - firstInbody.skeletal_muscle_kg).toFixed(1) : null;
  const fatChange = latestInbody && firstInbody
    ? (latestInbody.body_fat_pct - firstInbody.body_fat_pct).toFixed(1) : null;
  const consumedCalories = Math.round(todayNutrition?.calories || 0);
  const targetCalories = strategy?.daily_calories ? Math.round(strategy.daily_calories) : null;

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>📊 나의 변화 대시보드</h2>
      <button type="button" style={styles.recordButton} onClick={() => { setEntryMode("menu"); setError(""); }}>측정 기록하기</button>

      <div style={styles.summaryGrid}>
        {[
          { label: "현재 체중", value: latestWeight?.weight_kg ?? "미입력", unit: latestWeight ? "kg" : "", change: weightChange, good: weightChange <= 0 },
          { label: "골격근량", value: latestInbody?.skeletal_muscle_kg ?? "미입력", unit: latestInbody ? "kg" : "", change: muscleChange, good: muscleChange >= 0 },
          { label: "체지방률", value: latestInbody?.body_fat_pct ?? "미입력", unit: latestInbody ? "%" : "", change: fatChange, good: fatChange <= 0 },
          { label: "섭취 칼로리", value: consumedCalories, unit: "kcal", sub: targetCalories ? `목표 ${targetCalories}kcal` : "목표 -" },
          { label: "목표 칼로리", value: strategy?.daily_calories ?? "-", unit: "kcal", sub: `단백질 ${strategy?.protein_g ?? "-"}g` },
        ].map((item, i) => (
          <div key={i} style={styles.summaryCard}>
            <span style={styles.summaryLabel}>{item.label}</span>
            <span style={styles.summaryValue}>{item.value}</span>
            <span style={styles.summaryUnit}>{item.unit}</span>
            {item.change !== undefined && item.change !== null && (
              <span style={{ ...styles.summaryChange, color: item.good ? "#4CAF50" : "#f44336" }}>
                {item.change > 0 ? "+" : ""}{item.change}{item.unit}
              </span>
            )}
            {item.sub && <span style={styles.summaryChange}>{item.sub}</span>}
          </div>
        ))}
      </div>

      <div style={styles.chartCard}>
        <h3 style={styles.chartTitle}>체중 변화</h3>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={weightHistory}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="measured_date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
            <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} unit="kg" />
            <Tooltip formatter={(v) => [`${v}kg`, "체중"]} />
            <Line type="monotone" dataKey="weight_kg" stroke="#4CAF50" strokeWidth={2} dot={{ r: 4 }} name="체중" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div style={styles.chartCard}>
        <h3 style={styles.chartTitle}>체성분 변화</h3>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={compositionHistory}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="measured_date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
            <YAxis tick={{ fontSize: 11 }} unit="kg" />
            <Tooltip formatter={(v, n) => [`${v}kg`, n]} />
            <Legend />
            <Line type="monotone" dataKey="skeletal_muscle_kg" stroke="#2196F3" strokeWidth={2} dot={{ r: 4 }} name="골격근량" />
            <Line type="monotone" dataKey="body_fat_kg" stroke="#FF5722" strokeWidth={2} dot={{ r: 4 }} name="체지방량" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div style={styles.chartCard}>
        <h3 style={styles.chartTitle}>칼로리 섭취량 변화</h3>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={calorieHistory}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
            <YAxis tick={{ fontSize: 11 }} unit="kcal" />
            <Tooltip formatter={(v, n) => [`${Math.round(v)}kcal`, n === "calories" ? "섭취 칼로리" : "목표 칼로리"]} />
            <Legend />
            <Line type="monotone" dataKey="calories" stroke="#FF9800" strokeWidth={2} dot={{ r: 4 }} name="섭취 칼로리" />
            <Line type="monotone" dataKey="target_calories" stroke="#9E9E9E" strokeWidth={2} strokeDasharray="5 5" dot={false} name="목표 칼로리" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {strategy?.strategy_note && (
        <div style={styles.strategyCard}>
          <h3 style={styles.chartTitle}>현재 전략</h3>
          <p style={styles.strategyNote}>{strategy.strategy_note}</p>
        </div>
      )}

      {entryMode && <div style={styles.overlay} role="dialog" aria-modal="true" aria-label="측정 기록">
        <div style={styles.modal}>
          <button type="button" aria-label="닫기" style={styles.close} onClick={() => { setEntryMode(null); setApproval(null); }}>×</button>
          {!approval && entryMode === "menu" && <><h3>측정 기록하기</h3><div style={styles.modeButtons}>
            <button onClick={() => setEntryMode("weight")}>체중만 기록</button>
            <button onClick={() => setEntryMode("composition")}>체성분 직접 입력</button>
            <label style={styles.upload}>인바디 사진으로 입력<input aria-label="인바디 사진" type="file" accept="image/*" hidden onChange={async e => {
              const file=e.target.files?.[0]; if(!file) return; setBusy(true); setError("");
              try { const result=await uploadInbody(null,file); setApproval(result.proposal); }
              catch(err) { setError(err.message); } finally { setBusy(false); }
            }}/></label>
          </div></>}
          {!approval && ["weight", "composition"].includes(entryMode) && <form onSubmit={async e => {
            e.preventDefault(); setBusy(true); setError("");
            try {
              const base={measured_date:form.measured_date,weight_kg:Number(form.weight_kg)};
              const proposal=entryMode === "weight" ? await proposeWeight(base) : await proposeBodyComposition({...base,skeletal_muscle_kg:Number(form.skeletal_muscle_kg),body_fat_pct:Number(form.body_fat_pct)});
              setApproval(proposal);
            } catch(err) { setError(err.message); } finally { setBusy(false); }
          }}><h3>{entryMode === "weight" ? "체중 기록" : "체성분 직접 입력"}</h3>
            <label style={styles.field}>측정일<input type="date" required max={new Date().toISOString().slice(0,10)} value={form.measured_date} onChange={e=>setForm({...form,measured_date:e.target.value})}/></label>
            <label style={styles.field}>체중 (kg)<input type="number" step="0.1" min="0.1" max="500" required value={form.weight_kg} onChange={e=>setForm({...form,weight_kg:e.target.value})}/></label>
            {entryMode === "composition" && <><label style={styles.field}>골격근량 (kg)<input type="number" step="0.1" min="0.1" required value={form.skeletal_muscle_kg} onChange={e=>setForm({...form,skeletal_muscle_kg:e.target.value})}/></label>
            <label style={styles.field}>체지방률 (%)<input type="number" step="0.1" min="0" max="100" required value={form.body_fat_pct} onChange={e=>setForm({...form,body_fat_pct:e.target.value})}/></label></>}
            <button style={styles.submit} disabled={busy}>{busy ? "처리 중..." : "확인 내용 만들기"}</button>
          </form>}
          {approval && <ProposalCard proposal={approval} busy={busy} onDecision={async action => {
            setBusy(true); setError(""); try { await decideProposal(approval,action); setApproval(null); setEntryMode(null); if(action === "confirm") await fetchData(); }
            catch(err) { setError(err.message); } finally { setBusy(false); }
          }} onRevise={async payload => { setBusy(true); setError(""); try { setApproval(await reviseMeasurement(approval,payload)); } catch(err) { setError(err.message); } finally { setBusy(false); } }}/>}
          {error && <p role="alert" style={styles.error}>{error}</p>}
        </div>
      </div>}
    </div>
  );
}

const styles = {
  container: { padding: "20px 20px 32px", maxWidth: "700px", margin: "0 auto", overflowY: "auto", minHeight: "100%" },
  title: { fontSize: "20px", fontWeight: "bold", marginBottom: "16px" },
  recordButton: { width:"100%", border:0, borderRadius:12, padding:"12px", background:"#20835f", color:"white", fontWeight:700, marginBottom:16 },
  loading: { textAlign: "center", padding: "40px", color: "#999" },
  summaryGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: "8px", marginBottom: "16px" },
  summaryCard: { backgroundColor: "white", borderRadius: "12px", padding: "14px 10px", textAlign: "center", border: "1px solid #e0e0e0", display: "flex", flexDirection: "column", alignItems: "center" },
  summaryLabel: { fontSize: "11px", color: "#999", marginBottom: "4px" },
  summaryValue: { fontSize: "22px", fontWeight: "700", color: "#333" },
  summaryUnit: { fontSize: "11px", color: "#999" },
  summaryChange: { fontSize: "12px", fontWeight: "600", marginTop: "4px" },
  chartCard: { backgroundColor: "white", borderRadius: "12px", padding: "16px", marginBottom: "12px", border: "1px solid #e0e0e0" },
  chartTitle: { fontSize: "14px", fontWeight: "600", marginBottom: "12px", color: "#555" },
  strategyCard: { backgroundColor: "white", borderRadius: "12px", padding: "16px", border: "1px solid #e0e0e0" },
  strategyNote: { fontSize: "13px", color: "#666", lineHeight: 1.6 },
  overlay: { position:"fixed", inset:0, background:"rgba(18,35,29,.45)", display:"grid", placeItems:"center", padding:16, zIndex:1000 },
  modal: { position:"relative", width:"min(100%, 520px)", maxHeight:"90vh", overflowY:"auto", background:"white", borderRadius:18, padding:20, boxShadow:"0 20px 60px rgba(0,0,0,.2)" },
  close: { position:"absolute", right:12, top:8, border:0, background:"transparent", fontSize:28 },
  modeButtons: { display:"grid", gap:10, marginTop:18 },
  upload: { display:"block", textAlign:"center", padding:12, border:"1px solid #20835f", borderRadius:10, cursor:"pointer" },
  field: { display:"grid", gap:6, margin:"12px 0", fontSize:13 },
  submit: { width:"100%", border:0, borderRadius:10, padding:12, background:"#20835f", color:"white", fontWeight:700 },
  error: { color:"#b42318", background:"#fff1f0", padding:10, borderRadius:8 },
};
