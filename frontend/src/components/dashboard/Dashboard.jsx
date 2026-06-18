import { useState, useEffect } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer
} from "recharts";
import { getCalendar, getInbodyHistory, getCurrentStrategy, getCaloriesHistory } from "../../api/dietApi";

export default function Dashboard() {
  const [inbodyData, setInbodyData] = useState([]);
  const [strategy, setStrategy] = useState(null);
  const [todayNutrition, setTodayNutrition] = useState(null);
  const [calorieHistory, setCalorieHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const today = new Date().toISOString().split("T")[0];
      const [inbody, strat, todayData, calorieData] = await Promise.all([
        getInbodyHistory(),
        getCurrentStrategy(),
        getCalendar(today),
        getCaloriesHistory(),
      ]);
      setInbodyData(inbody);
      setStrategy(strat);
      setTodayNutrition(todayData.total || {});
      setCalorieHistory(calorieData.days || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  if (loading) return <div style={styles.loading}>로딩 중...</div>;

  const latestInbody = inbodyData[inbodyData.length - 1];
  const firstInbody = inbodyData[0];
  const weightChange = latestInbody && firstInbody
    ? (latestInbody.weight_kg - firstInbody.weight_kg).toFixed(1) : 0;
  const muscleChange = latestInbody && firstInbody
    ? (latestInbody.skeletal_muscle_kg - firstInbody.skeletal_muscle_kg).toFixed(1) : 0;
  const fatChange = latestInbody && firstInbody
    ? (latestInbody.body_fat_pct - firstInbody.body_fat_pct).toFixed(1) : 0;
  const consumedCalories = Math.round(todayNutrition?.calories || 0);
  const targetCalories = strategy?.daily_calories ? Math.round(strategy.daily_calories) : null;

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>📊 나의 변화 대시보드</h2>

      <div style={styles.summaryGrid}>
        {[
          { label: "현재 체중", value: latestInbody?.weight_kg ?? "-", unit: "kg", change: weightChange, good: weightChange < 0 },
          { label: "골격근량", value: latestInbody?.skeletal_muscle_kg ?? "-", unit: "kg", change: muscleChange, good: muscleChange >= 0 },
          { label: "체지방률", value: latestInbody?.body_fat_pct ?? "-", unit: "%", change: fatChange, good: fatChange < 0 },
          { label: "섭취 칼로리", value: consumedCalories, unit: "kcal", sub: targetCalories ? `목표 ${targetCalories}kcal` : "목표 -" },
          { label: "목표 칼로리", value: strategy?.daily_calories ?? "-", unit: "kcal", sub: `단백질 ${strategy?.protein_g ?? "-"}g` },
        ].map((item, i) => (
          <div key={i} style={styles.summaryCard}>
            <span style={styles.summaryLabel}>{item.label}</span>
            <span style={styles.summaryValue}>{item.value}</span>
            <span style={styles.summaryUnit}>{item.unit}</span>
            {item.change !== undefined && (
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
          <LineChart data={inbodyData}>
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
          <LineChart data={inbodyData}>
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
    </div>
  );
}

const styles = {
  container: { padding: "20px 20px 32px", maxWidth: "700px", margin: "0 auto", overflowY: "auto", minHeight: "100%" },
  title: { fontSize: "20px", fontWeight: "bold", marginBottom: "16px" },
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
};
