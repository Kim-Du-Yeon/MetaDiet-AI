import { useEffect, useState } from 'react';
import MealNutritionFacts from './MealNutritionFacts';

const mealTypes = { breakfast: '아침', lunch: '점심', dinner: '저녁', snack: '간식' };
export default function MealProposalEditor({ proposal, busy, onRevise, onChanged, budget }) {
  const payload = proposal.payload;
  const initial = () => ({ log_date: payload.log_date,
    meal_type: new Set(payload.meals.map(meal => meal.meal_type)).size > 1 ? null : payload.meals[0]?.meal_type || 'dinner',
    items: payload.meals.map(meal => ({ amount: meal.nutrition_metadata?.portion?.amount ?? meal.quantity_g,
      unit: meal.nutrition_metadata?.portion?.unit ?? 'g' })) });
  const [draft, setDraft] = useState(initial);
  useEffect(() => { setDraft(initial()); onChanged(false); }, [proposal]); // eslint-disable-line react-hooks/exhaustive-deps
  const change = next => { setDraft(next); onChanged(JSON.stringify(next) !== JSON.stringify(initial())); };
  const total = payload.meals.reduce((sum, meal) => sum + meal.calories, 0);
  const editable = payload.meals.every(meal => meal.food_id && meal.source !== 'user_label');
  const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(new Date());
  const changed = JSON.stringify(draft) !== JSON.stringify(initial());
  const excluded = [...new Set(payload.meals.flatMap(meal => meal.nutrition_metadata?.excluded_foods || []))];
  return <div className="meal-preview">
    {editable ? <div className="proposal__fields"><label>섭취일<input type="date" value={draft.log_date} disabled={busy}
      max={proposal.kind === 'intake' ? today : undefined} onChange={e => change({ ...draft, log_date: e.target.value })} /></label>
      <label>끼니<select value={draft.meal_type || ''} disabled={busy} onChange={e => change({ ...draft, meal_type: e.target.value || null })}>
        {new Set(payload.meals.map(meal => meal.meal_type)).size > 1 && <option value="">기존 끼니 유지</option>}
        {Object.entries(mealTypes).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div> : <p>{payload.log_date}</p>}
    <ul className="proposal__meals">{payload.meals.map((meal, index) => {
      const portion = meal.nutrition_metadata?.portion;
      return <li key={index}><div><strong>{portion?.display_name || meal.food_name}</strong>
        <div className="meal-preview__badges">
          <span className="meal-preview__serving">{portion?.defaulted ? `1인분 · ${meal.quantity_g}g` : `${portion && portion.unit !== 'g' ? `${portion.amount}${portion.unit} · ` : ''}${meal.quantity_g}g`}</span>
          {editable && <span className="meal-preview__editable">아래에서 분량 수정 가능</span>}
          {portion?.representative && <span className="meal-preview__estimate">대표 기준 · 대략값</span>}
        </div>
        {portion?.defaulted && <p className="meal-preview__default-note">앱 기본 분량으로 계산했어요.</p>}
        <MealNutritionFacts meal={meal} />
        {editable && <><button type="button" className="proposal__secondary" disabled={busy} aria-label={`${index + 1}번 음식 ${draft.items[index].exclude ? '제외 취소' : '제외하기'}`} onClick={() => change({ ...draft, items: draft.items.map((item, i) => { if (i !== index) return item; const { exclude, ...rest } = item; return exclude ? rest : { ...rest, exclude: true }; }) })}>{draft.items[index].exclude ? '제외 취소' : '제외하기'}</button>{draft.items[index].exclude && <p>제외 예정 · 다시 계산하면 합계에서 빠져요.</p>}<div className="meal-preview__portion"><label>분량<input aria-label={`${index + 1}번 음식 분량`} type="number" min="0.01" max="10000" step="any"
          disabled={busy || draft.items[index].exclude} value={draft.items[index].amount} onChange={e => change({ ...draft, items: draft.items.map((item, i) => i === index ? { ...item, amount: Number(e.target.value) } : item) })} /></label>
          <label>단위<select aria-label={`${index + 1}번 음식 단위`} disabled={busy || draft.items[index].exclude} value={draft.items[index].unit}
            onChange={e => change({ ...draft, items: draft.items.map((item, i) => i === index ? { ...item, unit: e.target.value } : item) })}>
            {[...new Set(['g', ...(portion?.unit_grams ? Object.keys(portion.unit_grams) : portion?.default_unit ? [portion.default_unit, '회분', '인분'] : [])])].map(unit => <option key={unit}>{unit}</option>)}</select></label></div></>}
        <details><summary>출처·상세 정보</summary>{portion?.basis_note && <p>{portion.basis_note}</p>}<small>{meal.food_name} · {({ csv: '국가표준식품성분표', mfds: '식약처', user_label: '사용자 영양표' })[meal.source] || meal.source}
          {meal.nutrition_metadata?.manufacturer && ` · ${meal.nutrition_metadata.manufacturer}`} · 나트륨 {meal.sodium_mg ?? '미입력'}mg</small></details></div></li>;
    })}</ul>
    {excluded.length > 0 && <p role="status">기록에서 제외: {excluded.join(', ')}. 합계에도 포함되지 않았어요.</p>}
    <div className="proposal__macros"><strong>합계 {Math.round(total)} kcal</strong>
      {['carbs_g', 'protein_g', 'fat_g'].map((key, index) => <span key={key}>{['탄수화물', '단백질', '지방'][index]} {payload.meals.reduce((sum, meal) => sum + meal[key], 0).toFixed(1)}g</span>)}</div>
    {proposal.kind === 'intake' && payload.log_date === today && budget?.target > 0 && <p>이 식사를 기록하면 오늘 남는 칼로리: <strong>{Math.round(budget.target - budget.calories - total)} kcal</strong> (아직 섭취량에 반영되지 않았어요)</p>}
    {draft.items.every(item => item.exclude) && <p role="status">모두 제외하려면 아래 취소 버튼을 눌러주세요.</p>}
    {changed && <p role="status">변경한 분량은 다시 계산한 뒤 기록할 수 있어요. 위 영양값은 변경 전 값입니다.</p>}
    {editable && <button className="proposal__secondary" disabled={busy || !changed || draft.items.every(item => item.exclude) || draft.items.some(item => !item.exclude && !(item.amount > 0))}
      onClick={() => onRevise(draft)}>수정한 분량 다시 계산</button>}
  </div>;
}
