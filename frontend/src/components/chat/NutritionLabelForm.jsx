import { useRef, useState } from "react";
import { proposeNutritionLabel } from "../../api/dietApi";
import "./NutritionLabelForm.css";

const numericFields = [["basis_g", "영양표 기준량 (g)"], ["quantity_g", "먹은 양 (g)"], ["calories", "열량 (kcal)"], ["protein_g", "단백질 (g)"], ["carbs_g", "탄수화물 (g)"], ["fat_g", "지방 (g)"]];
export default function NutritionLabelForm({ threadId, onProposal, onClose, onLabel, initialValues = {}, disabled = false }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(null);
  async function submit(event) {
    event.preventDefault();
    if (busy || disabled) return;
    const data = Object.fromEntries(new FormData(event.currentTarget));
    numericFields.forEach(([key]) => { data[key] = Number(data[key]); });
    setBusy(true); setError("");
    requestId.current ||= window.crypto.randomUUID();
    try { if (onLabel) await onLabel(data);
      else onProposal(await proposeNutritionLabel({ ...data, thread_id: threadId, request_id: requestId.current })); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  return <form className="nutrition-label" onSubmit={submit} onChange={() => { requestId.current = null; }} aria-label="제품 영양표 입력">
    <h3>제품 영양표 직접 입력</h3>
    <p>포장에 적힌 기준량과 영양값을 입력해주세요. 다음 확인 카드에서 확정해야 저장됩니다.</p>
    <fieldset disabled={busy || disabled}>
      <label>제품명 (필수)<input name="food_name" required maxLength={200} defaultValue={initialValues.food_name || ''} /></label>
      <label>제조사 (선택)<input name="manufacturer" maxLength={200} /></label>
      {numericFields.map(([key, label]) => <label key={key}>{label} (필수)<input name={key} type="number" step="any" min={key.endsWith("_g") && ["basis_g", "quantity_g"].includes(key) ? "0.01" : "0"} defaultValue={initialValues[key] ?? ''} required /></label>)}
      {!onLabel && <><label>섭취일 (필수)<input name="log_date" type="date" required /></label>
      <label>식사 구분<select name="meal_type" defaultValue="snack"><option value="breakfast">아침</option><option value="lunch">점심</option><option value="dinner">저녁</option><option value="snack">간식</option></select></label></>}
    </fieldset>
    {error && <p role="alert">{error}</p>}
    <button disabled={busy || disabled} type="submit">영양값 확인하기</button>
    <button disabled={busy || disabled} type="button" onClick={onClose}>닫기</button>
  </form>;
}
