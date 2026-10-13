import { useState } from 'react';
import './ProductChoiceCards.css';

const fields = [['basis_g','기준량 (g)'], ['quantity_g','먹은 양 (g)'], ['calories','열량 (kcal)'],
  ['carbs_g','탄수화물 (g)'], ['protein_g','단백질 (g)'], ['fat_g','지방 (g)']];

function FoodChoice({ item, choice, onChange, busy }) {
  const action = choice?.action;
  return <fieldset disabled={busy}>
    <legend>{item.query}</legend>
    <p>정확한 정보를 몰라도 제외하고 진행할 수 있어요.</p>
    <div className="product-choices__actions">
      {item.generic_available && <button type="button" aria-pressed={action === 'generic'} onClick={() => onChange({action:'generic'})}>일반 아이스크림 기준 사용</button>}
      <button type="button" aria-pressed={action === 'label'} onClick={() => onChange({action:'label', label:choice?.label || {food_name:item.query}})}>기입하기</button>
      <button type="button" aria-pressed={action === 'exclude'} onClick={() => onChange({action:'exclude'})}>제외하기</button>
    </div>
    {action === 'generic' && <p>제품 고유 영양값이 아닌 일반 아이스크림 대략값 · {item.quantity_g}g으로 계산해요. 다음 카드에서 수정할 수 있어요.</p>}
    {action === 'exclude' && <p>이 음식은 기록과 합계에서 제외돼요.</p>}
    {action === 'label' && <div className="meal-choice-fields">
      {fields.map(([key, label]) => <label key={key}>{label}<input aria-label={label} type="number" step="any"
        min={['basis_g','quantity_g'].includes(key) ? '0.01' : '0'} required value={choice.label?.[key] ?? ''}
        onChange={event => onChange({...choice, label:{...choice.label, [key]:event.target.value}})} /></label>)}
      <p>입력이 번거로우면 위의 제외하기 또는 전체 취소를 누르세요.</p>
    </div>}
  </fieldset>;
}

export default function MealChoiceCards({ selection, busy, error, onResolve, onCancel }) {
  const [choices, setChoices] = useState({});
  const ready = selection.items.every(item => choices[item.index]?.action);
  function submit(event) {
    event.preventDefault();
    if (!ready) return;
    onResolve(selection.items.map(item => {
      const choice = choices[item.index];
      return {index:item.index, action:choice.action, ...(choice.action === 'label' ? {label:{...choice.label,
        ...Object.fromEntries(fields.map(([key]) => [key, Number(choice.label[key])]))}} : {})};
    }));
  }
  return <section className="product-choices" aria-label="음식 기록 선택">
    <h3>이 음식만 어떻게 기록할까요?</h3>
    <p>나머지 음식은 기본 분량으로 계산해요. 아직 저장되지 않았어요.</p>
    <form onSubmit={submit}>
      {selection.items.map(item => <FoodChoice key={item.index} item={item} choice={choices[item.index]} busy={busy}
        onChange={choice => setChoices({...choices, [item.index]:choice})} />)}
      {error && <p role="alert">{error}</p>}
      <div className="product-choices__actions">
        <button disabled={busy || !ready}>선택 적용</button>
        <button type="button" disabled={busy} onClick={() => onResolve(selection.items.map(item => ({index:item.index,action:'exclude'})))}>미확인 음식 모두 스킵</button>
        <button type="button" disabled={busy} onClick={onCancel}>전체 취소</button>
      </div>
    </form>
  </section>;
}
