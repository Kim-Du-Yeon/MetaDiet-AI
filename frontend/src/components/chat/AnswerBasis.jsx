import { useId, useState } from 'react';
const labels = { breakfast: '아침', lunch: '점심', dinner: '저녁', snack: '간식' };
const sourceNames = {csv:'국가표준식품성분표', mfds:'식약처', user_label:'사용자 영양표', llm_estimated:'기존 추정값'};
function safeLink(value) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}
export default function AnswerBasis({ basis }) {
  const id = useId();
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [recordsOpen, setRecordsOpen] = useState(false);
  if (!basis) return null;
  const count = basis.documents?.length || 0;
  return <section className="answer-basis" aria-label="참고한 기록·근거">
    <div className="answer-basis__actions">
      <button type="button" aria-expanded={sourcesOpen} aria-controls={`${id}-sources`}
        onClick={() => setSourcesOpen(!sourcesOpen)}>출처 보기 · {count}개</button>
      <button type="button" aria-expanded={recordsOpen} aria-controls={`${id}-records`}
        onClick={() => setRecordsOpen(!recordsOpen)}>내 기록·계산 근거 보기</button>
    </div>
    <div id={`${id}-records`} hidden={!recordsOpen}>
    <p>{basis.notice}</p>
    <strong>내 기록</strong>
    {basis.records ? <><p>{basis.records.date} · 확정 기록 {basis.records.meals.length}건</p>
      <ul>{basis.records.meals.map((meal, i) => <li key={i}>{labels[meal.meal_type] || '식사'} · {meal.food_name} {meal.quantity_g}g</li>)}</ul>
      <table><caption>조회한 섭취량과 목표</caption><thead><tr><th>항목</th><th>확정 섭취</th><th>목표</th></tr></thead>
        <tbody>{[['calories','daily_calories','열량','kcal'],['protein_g','protein_g','단백질','g'],['carbs_g','carbs_g','탄수화물','g'],['fat_g','fat_g','지방','g']].map(([key,target,label,unit]) =>
          <tr key={key}><th>{label}</th><td>{basis.records.totals[key]} {unit}</td><td>{basis.targets?.[target] == null ? '미확인' : `${basis.targets[target]} ${unit}`}</td></tr>)}</tbody></table>
      </> : <p>이번 요청에서 확정 섭취 기록 조회를 확인하지 못했어요.</p>}
    <strong>영양 계산</strong>
    {basis.calculations?.length ? <ul>{basis.calculations.map((item,i) => <li key={i}>{item.food_name} · {sourceNames[item.source] || item.source}{item.basis && ` · ${item.basis}`}</li>)}</ul>
      : <p>이번 답변에서 별도 식품 영양 계산은 확인되지 않았어요.</p>}
    </div>
    <div id={`${id}-sources`} hidden={!sourcesOpen}>
    <strong>답변에 인용된 출처</strong>
    {basis.documents?.length ? <ol>{basis.documents.map((doc,i) => <li key={i} className="answer-basis__source">
      <strong>[근거 {i + 1}] {doc.source}</strong>
      {' · '}페이지 {doc.page || '미확인'}
      {doc.excerpt && <details><summary>인용 내용 보기</summary><blockquote>{doc.excerpt}</blockquote></details>}
      {safeLink(doc.source_url) ? <a href={safeLink(doc.source_url)} target="_blank" rel="noopener noreferrer">원문 보기 ↗</a>
        : <p className="answer-basis__muted">원문 링크가 제공되지 않은 자료예요.</p>}</li>)}</ol> : <p>답변에 명시적으로 연결된 문서 인용이 없어요.</p>}
    {basis.limitation && <p><strong>한계</strong> · {basis.limitation}</p>}
    <p>문서 인용 표시는 근거 연결을 돕는 정보이며, 답변 전체의 정확성을 보장하지 않아요.</p>
    </div>
  </section>;
}
