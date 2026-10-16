import { useEffect, useState } from 'react';

export default function CoachingReview({ details, busy, onProvide }) {
  const [editing, setEditing] = useState(false);
  const [skipped, setSkipped] = useState(false);
  const [value, setValue] = useState('');
  useEffect(() => { setEditing(false); setSkipped(false); setValue(''); }, [details]);
  if (details?.optional_input !== 'measurements') return null;
  return <section className="coaching-review" aria-label="추가 기록 선택">
    <strong>체중·체성분 추세 확인은 선택이에요</strong>
    <p>변화를 판단할 측정 기록이 부족해요. 입력하지 않아도 위의 확인된 기록 분석을 이용할 수 있어요.</p>
    {skipped ? <p role="status">추가 입력을 건너뛰었어요. 기록은 변경되지 않았어요.</p> : <>
      {!editing && <button type="button" disabled={busy} onClick={() => setEditing(true)}>입력</button>}
      <button type="button" disabled={busy} onClick={() => { setSkipped(true); setEditing(false); }}>건너뛰기</button>
      {editing && <form onSubmit={event => { event.preventDefault(); if (value.trim() && !busy) onProvide(value.trim()); }}>
        <label>추가 측정 기록 (선택)<textarea value={value} disabled={busy} maxLength={1000}
          placeholder="측정 날짜와 알고 있는 체중·체성분을 적어주세요. 저장은 별도 확인 후 진행해요."
          onChange={event => setValue(event.target.value)} /></label>
        <button type="submit" disabled={busy || !value.trim()}>확인 요청</button>
        <button type="button" disabled={busy} onClick={() => {setEditing(false);setValue('');}}>취소</button>
      </form>}
    </>}
  </section>;
}
