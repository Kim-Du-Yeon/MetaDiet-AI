import {useEffect, useState} from 'react';
import {updateAdminFeedback, getAdminFeedbackAssignees} from '../api/dietApi';
import FeedbackHistory from './FeedbackHistory';
import {feedbackStatuses, feedbackCategories, feedbackDate} from './feedbackOptions';

export default function FeedbackReview({feedback, onSaved, onReload, onClose}) {
  const [status, setStatus] = useState(feedback.status);
  const [note, setNote] = useState(feedback.admin_note || '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [assignee,setAssignee]=useState(feedback.assignee_id||'');
  const [assignees,setAssignees]=useState(null), [assigneeError,setAssigneeError]=useState(''), [retry,setRetry]=useState(0);
  useEffect(()=>{
    let active=true;setAssigneeError('');
    getAdminFeedbackAssignees().then(result=>{if(active)setAssignees(result?.items||[]);})
      .catch(reason=>{if(active)setAssigneeError(reason.message);});
    return()=>{active=false;};
  },[retry]);
  useEffect(() => {
    setStatus(feedback.status); setNote(feedback.admin_note || '');
    setAssignee(feedback.assignee_id||'');
  }, [feedback]);
  const save = async event => {
    event.preventDefault(); if (busy) return;
    setBusy(true); setMessage('');
    try {
      const assignment=assignee===(feedback.assignee_id||'')?{}:{assignee_id:assignee||null};
      const saved = await updateAdminFeedback(feedback.id, {version:feedback.version,status,admin_note:note,...assignment});
      onSaved(saved); setMessage('저장했습니다.');
    } catch (error) { setMessage(error.message); }
    finally { setBusy(false); }
  };
  return <section className="feedback-review" aria-label="피드백 상세">
    <h3>피드백 상세</h3>
    <p>{feedbackCategories[feedback.category]} · {feedback.rating}점 · {feedbackDate(feedback.created_at)}</p>
    <p className="feedback-review__opinion">{feedback.comment || '작성된 의견이 없습니다.'}</p>
    <form onSubmit={save}>
      <label>처리 상태<select value={status} disabled={busy} onChange={e=>setStatus(e.target.value)}>
        {Object.entries(feedbackStatuses).map(([value,label])=><option value={value} key={value}>{label}</option>)}
      </select></label>
      <label>담당자<select aria-label="담당자" value={assignee} disabled={busy||!assignees} onChange={e=>setAssignee(e.target.value)}>
        <option value="">미지정</option>
        {assignee && !assignees?.some(row=>row.id===assignee) && <option value={assignee}>기존 담당자 (현재 허용 목록에 없음)</option>}
        {assignees?.map(row=><option value={row.id} key={row.id}>{row.email}</option>)}
      </select></label>
      {!assignees && !assigneeError && <p role="status">담당자 목록을 불러오는 중입니다.</p>}
      {assigneeError && <p role="alert">{assigneeError} <button type="button" onClick={()=>setRetry(n=>n+1)}>담당자 다시 시도</button></p>}
      <label>관리자 메모<textarea value={note} maxLength={1000} rows={4} disabled={busy} onChange={e=>setNote(e.target.value)}/></label>
      <small>최대1000자 · 재현 조건과 조치만 적고 비밀번호·신체 정보 등은 남기지 마세요.</small>
      <p>최근 변경: {feedbackDate(feedback.updated_at)} · 버전 {feedback.version}</p>
      {message && <p role="status">{message}</p>}
      <div className="feedback-review__actions">
        <button type="submit" disabled={busy}>{busy?'저장 중…':'처리 내용 저장'}</button>
        <button type="button" disabled={busy} onClick={onReload}>최신 내용 다시 불러오기</button>
        <button type="button" disabled={busy} onClick={onClose}>수정 취소·닫기</button>
      </div>
      <small>다시 불러오기·닫기는 저장하지 않은 수정 내용을 버립니다.</small>
    </form>
    <FeedbackHistory key={feedback.id} feedbackId={feedback.id} version={feedback.version}/>
  </section>;
}
