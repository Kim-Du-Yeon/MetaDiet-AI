import { useState } from "react";
import { nutritionLookup } from "../../api/dietApi";
import "./NutritionLabelForm.css";

export default function FoodProductSearch({ onSelect, onClose, contextRequest, onProduct, initialName = '', initialGrams = '', disabled = false }) {
  const [query, setQuery] = useState(initialName);
  const [grams, setGrams] = useState(initialGrams);
  const [candidates, setCandidates] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function select(candidate) {
    if (busy || disabled) return;
    if (onProduct) {
      setBusy(true); setMessage('');
      try { await onProduct({food_id:candidate.food_id, quantity_g:Number(grams)}); }
      catch (error) { setMessage(error.message); }
      finally { setBusy(false); }
      return;
    }
    const food = `${candidate.name} ${grams}g`;
    onSelect({
      request: contextRequest ? `${contextRequest}\n제품 선택: ${candidate.food_id} / ${food}` : `제품 선택: ${candidate.food_id} / ${food} 오늘 먹었어. 기록만 해줘.`,
      display: contextRequest ? `${food} 제품을 선택했어요.` : `${food} 오늘 먹었어. 기록만 해줘.`
    });
  }
  async function search(event) {
    event.preventDefault(); if (busy || disabled) return; setBusy(true); setMessage(""); setCandidates([]);
    try {
      const response = await nutritionLookup([{ name: query, quantity_g: Number(grams), food_kind: "product" }]);
      const result = response.results[0];
      setCandidates(result.candidates || (result.food_id ? [{ food_id: result.food_id, name: result.food_name, ...result.nutrition_metadata }] : []));
      if (result.status === "not_found" || result.status === "missing_nutrients") setMessage("계산 가능한 제품을 찾지 못했습니다. 제품 영양표 입력을 이용해주세요.");
    } catch (error) { setMessage(error.message); }
    finally { setBusy(false); }
  }
  return <section className="nutrition-label" aria-label="식품 제품 선택">
    <h3>정확한 제품 찾기</h3><p>오늘 섭취한 제품의 제조사와 용량을 확인하고 선택해주세요. 선택 후에도 확인 카드에서 확정해야 저장됩니다.</p>
    <form onSubmit={search}><fieldset disabled={busy || disabled}>
      <label>제품명<input required value={query} onChange={event => { setQuery(event.target.value); setCandidates([]); }} /></label>
      <label>먹은 양 (g)<input required type="number" min="0.01" max="10000" step="any" value={grams} onChange={event => { setGrams(event.target.value); setCandidates([]); }} /></label>
    </fieldset><button disabled={busy || disabled}>제품 검색</button></form>
    {message && <p role="status">{message}</p>}
    <ul>{candidates.map(candidate => <li key={candidate.food_id}><strong>{candidate.name}</strong><p>{candidate.food_kind === "standard" ? "일반 음식 표준값" : `${candidate.manufacturer || "제조사 정보 없음"} · ${candidate.package_text || "포장 용량 정보 없음"}`}</p><button type="button" disabled={busy || disabled} onClick={() => select(candidate)}>{candidate.food_kind === "standard" ? "표준값으로 기록 검토" : "이 제품 선택"}</button></li>)}</ul>
    <button type="button" disabled={busy || disabled} onClick={onClose}>닫기</button>
  </section>;
}
