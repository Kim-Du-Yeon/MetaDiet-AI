import { useEffect, useState } from "react";
import "./ProposalCard.css";
import MealProposalEditor from "./MealProposalEditor";
import ProductCorrection from './ProductCorrection';

const labels = { intake: "실제 섭취 기록", plan: "식단 계획", measurement: "인바디 측정", weight: "체중 기록", strategy: "전략 변경", meal_delete: "섭취 기록 삭제", meal_replace: "섭취 기록 수정" };
const fields = { measured_date: "측정일", weight_kg: "체중 (kg)", skeletal_muscle_kg: "골격근량 (kg)", body_fat_kg: "체지방량 (kg)", body_fat_pct: "체지방률 (%)" };

function EvidenceList({ evidence = [] }) {
  if (!evidence.length) return null;
  return <section className="proposal__evidence" aria-labelledby="proposal-evidence-heading">
    <h4 id="proposal-evidence-heading">참고 근거</h4>
    <div className="proposal__sources">{evidence.map((item, index) =>
      <article className="proposal__source" key={`${item.source}-${item.page}-${index}`}>
        <strong>{item.source}</strong>
        <span>{item.page !== undefined ? `${item.page}쪽` : "페이지 정보 없음"}</span>
        {(item.edition || item.population) && <small>{[item.edition, item.population].filter(Boolean).join(" · ")}</small>}
      </article>)}</div>
  </section>;
}

export default function ProposalCard({ proposal, busy, onDecision, onRevise, budget, onReplaceProduct }) {
  const [draft, setDraft] = useState(proposal.payload);
  useEffect(() => setDraft(proposal.payload), [proposal]);
  const [mealChanged, setMealChanged] = useState(false);
  const [productEditing, setProductEditing] = useState(false);
  useEffect(() => setProductEditing(false), [proposal]);
  const payload = proposal.payload;
  const changed = JSON.stringify(draft) !== JSON.stringify(payload);
  return <section aria-label="확인 대기 제안" className="proposal">
    <div className="proposal__eyebrow">사용자 확인 필요 · v{proposal.version}</div>
    <h3>{labels[proposal.kind]} 확인</h3>
    {proposal.kind === "plan" && <p className="proposal__notice">계획을 채택해도 실제 섭취량에는 반영되지 않습니다.</p>}
    {payload.expected && <p>대상: {payload.expected.food_name} · {payload.expected.quantity_g}g{payload.meal ? ` → ${payload.meal.food_name} ${payload.meal.quantity_g}g` : " (삭제)"}</p>}
    {payload.meals && <MealProposalEditor proposal={proposal} busy={busy || productEditing} onRevise={onRevise} onChanged={setMealChanged} budget={budget} />}
    {proposal.kind === 'intake' && onReplaceProduct && <ProductCorrection key={`${proposal.id}-${proposal.version}`} proposal={proposal} busy={busy || mealChanged} onReplace={onReplaceProduct} onEditingChange={setProductEditing} />}
    {["measurement", "weight"].includes(proposal.kind) && <div className="proposal__fields">{Object.entries(fields).filter(([key]) => proposal.kind === "measurement" || ["measured_date", "weight_kg"].includes(key)).map(([key, label]) =>
      <label key={key}><span>{label}</span><input
        type={key === "measured_date" ? "date" : "number"} step="any" value={draft[key] ?? ""} disabled={busy}
        onChange={event => setDraft({ ...draft, [key]: key === "measured_date" ? event.target.value : Number(event.target.value) })} /></label>)}
      <button className="proposal__secondary" disabled={busy || !changed} onClick={() => onRevise(draft)}>수정한 수치로 다시 제안</button></div>}
    {proposal.kind === "strategy" && <><p className="proposal__date">{payload.effective_date}부터 적용</p><div className="proposal__macros">
      <strong>{payload.daily_calories} kcal</strong><span>단백질 {payload.protein_g}g</span><span>탄수화물 {payload.carbs_g}g</span><span>지방 {payload.fat_g}g</span>
    </div><p>{payload.strategy_note}</p><EvidenceList evidence={payload.evidence} /></>}
    <div className="proposal__actions">
      <button className="proposal__confirm" disabled={busy || changed || mealChanged || productEditing} onClick={() => onDecision("confirm")}>{proposal.kind === "intake" ? "이대로 기록" : "이 내용 확정"}</button>
      <button className="proposal__cancel" disabled={busy} onClick={() => onDecision("cancel")}>취소</button>
    </div>
  </section>;
}
