export default function CoachingActions({ busy, onRecommend }) {
  return <div className="chat-actions" aria-label="다음 식사 코칭">
    {['점심', '저녁'].map(meal => <button type="button" key={meal} disabled={busy}
      onClick={() => onRecommend({ request: `${meal} 추천해줘`, display: `${meal} 추천` })}>{meal} 추천</button>)}
    {busy && <p className="chat-actions__status" role="status">현재 답변을 준비하고 있어요.</p>}
  </div>;
}
