import { useState } from "react";
import "./ProductChoiceCards.css";

export default function ProductChoiceCards({ selection, busy, onSelect, onSearch }) {
  const [choices, setChoices] = useState({});
  const [amounts, setAmounts] = useState({});
  const items = selection.items;
  const ready = items.every((item, index) => choices[index] && Number(amounts[index] ?? item.quantity_g) > 0 && Number(amounts[index] ?? item.quantity_g) <= 10000);
  function submit(event) {
    event.preventDefault();
    if (!ready) return;
    const selected = items.map((item, index) => ({
      candidate: item.candidates.find(candidate => candidate.food_id === choices[index]),
      grams: Number(amounts[index] ?? item.quantity_g)
    }));
    onSelect({
      request: selection.request + "\n" + selected.map(({ candidate, grams }) => `제품 선택: ${candidate.food_id} / ${candidate.name} ${grams}g`).join("\n"),
      display: selected.map(({ candidate, grams }) => `${candidate.name} ${grams}g`).join(", ") + " 제품을 선택했어요."
    });
  }
  return <section className="product-choices" aria-label="제품 확인">
    <h3>제품만 확인해주세요</h3>
    <p>일반 음식은 표준값을 사용해요. 드신 제품을 고르면 전체 식사를 다시 검토하며, 아직 저장하지 않아요.</p>
    <form onSubmit={submit}>
      {items.map((item, index) => <fieldset key={`${item.query}-${index}`} disabled={busy}>
        <legend>{item.query}</legend>
        <label>먹은 양 (g)<input aria-label={`${item.query} 먹은 양 (g)`} type="number" required min="0.01" max="10000" step="any"
          value={amounts[index] ?? item.quantity_g ?? ""} onChange={event => setAmounts({ ...amounts, [index]: event.target.value })} /></label>
        <div className="product-choices__list">{item.candidates.map(candidate => <label key={candidate.food_id} className="product-choices__option">
          <input type="radio" name={`product-${index}`} checked={choices[index] === candidate.food_id}
            onChange={() => setChoices({ ...choices, [index]: candidate.food_id })} />
          <span><strong>{candidate.name}</strong><small>{candidate.manufacturer || "제조사 정보 없음"} · {candidate.package_text || "용량 정보 없음"}</small></span>
        </label>)}</div>
        {!item.candidates.length && <p>등록된 제품이 없어요. 제품명과 영양표를 확인해주세요.</p>}
      </fieldset>)}
      <div className="product-choices__actions"><button disabled={busy || !ready}>선택한 제품으로 다시 검토</button>
        {onSearch && <button type="button" disabled={busy} onClick={onSearch}>다른 제품 찾기</button>}</div>
    </form>
  </section>;
}
