import { useEffect, useState } from "react";
import { getAdminAnalytics } from "../api/dietApi";

const percent = (value) => `${Math.round((value || 0) * 100)}%`;
const seconds = (value) => value ? `${(value / 1000).toFixed(1)}초` : "-";

export default function AdminAnalytics() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState(undefined);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setError("");
    getAdminAnalytics(days)
      .then((result) => { if (active) setData(result); })
      .catch((reason) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [days]);

  if (data === null) return null;
  if (data === undefined && !error) return null;
  if (error) return <section className="settings-card" role="alert">{error}</section>;

  const cards = [
    ["오늘 활성 사용자", data.active_users.daily],
    ["7일 활성 사용자", data.active_users.weekly],
    ["온보딩 완료율", percent(data.funnel.onboarding_rate)],
    ["첫 식사 기록률", percent(data.funnel.first_meal_rate)],
    ["Agent 성공률", percent(data.agent.success_rate)],
    ["응답 지연 p95", seconds(data.agent.latency_p95_ms)],
  ];
  return (
    <section className="settings-card admin-analytics" aria-labelledby="admin-analytics-title">
      <div className="analytics-heading">
        <div><p className="settings-eyebrow">BETA OPERATIONS</p><h2 id="admin-analytics-title">제품 운영 지표</h2></div>
        <select aria-label="조회 기간" value={days} onChange={(event) => setDays(Number(event.target.value))}>
          <option value={1}>24시간</option><option value={7}>7일</option><option value={30}>30일</option><option value={90}>90일</option>
        </select>
      </div>
      <div className="analytics-grid">{cards.map(([label, value]) => (
        <article key={label}><span>{label}</span><strong>{value}</strong></article>
      ))}</div>
      <p className="analytics-privacy">대화 내용과 건강 수치는 수집하지 않고 단계·성공 여부·지연만 집계합니다.</p>
    </section>
  );
}
