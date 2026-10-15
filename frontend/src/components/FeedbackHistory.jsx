import {useEffect, useState} from 'react';
import {getAdminFeedbackHistory} from '../api/dietApi';
import {feedbackStatuses, feedbackDate} from './feedbackOptions';

const assignee = (id, email) => email || (id ? '삭제된 관리자' : '미지정');

export default function FeedbackHistory({feedbackId, version}) {
  const [open,setOpen]=useState(false), [cursor,setCursor]=useState(null), [reload,setReload]=useState(0);
  const [data,setData]=useState(null), [error,setError]=useState(''), [busy,setBusy]=useState(false);
  useEffect(()=>{setCursor(null);setData(null);},[feedbackId,version]);
  useEffect(()=>{
    if(!open)return;
    let active=true;setBusy(true);setError('');
    getAdminFeedbackHistory(feedbackId,cursor).then(result=>{
      if(active)setData(old=>({...result,items:cursor?[...(old?.items||[]),...(result?.items||[])]:result?.items||[]}));
    }).catch(reason=>{if(active)setError(reason.message);}).finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;};
  },[feedbackId,version,open,cursor,reload]);
  return <section className="feedback-history" aria-label="변경 이력">
    <button type="button" aria-expanded={open} onClick={()=>{
      if(!open){setCursor(null);setData(null);}setOpen(value=>!value);
    }}>{open?'변경 이력 접기':'변경 이력 보기'}</button>
    {open && <>
      <p>기능 적용 이후의 저장 이력입니다. 최근 변경부터 표시합니다.</p>
      {busy && <p role="status">이력을 불러오는 중입니다.</p>}
      {error && <p role="alert">{error} <button type="button" onClick={()=>setReload(n=>n+1)}>이력 다시 시도</button></p>}
      {data?.items.length===0 && !busy && !error && <p>아직 변경 이력이 없습니다.</p>}
      <ol>{data?.items.map(row=><li key={row.id}>
        <p><strong>버전 {row.version}</strong> · {feedbackDate(row.created_at)} · 변경자: {row.actor_email||'삭제된 관리자'}</p>
        <p>상태: {feedbackStatuses[row.before_status]} → {feedbackStatuses[row.after_status]}</p>
        <p>담당자: {assignee(row.before_assignee_id,row.before_assignee_email)} → {assignee(row.after_assignee_id,row.after_assignee_email)}</p>
        {row.before_note!==row.after_note && <details><summary>메모 변경 내용</summary>
          <p>이전</p><p className="feedback-review__opinion">{row.before_note||'없음'}</p>
          <p>이후</p><p className="feedback-review__opinion">{row.after_note||'없음'}</p>
        </details>}
      </li>)}</ol>
      {data?.has_more && <button type="button" disabled={busy||!!error} onClick={()=>setCursor(data.next_before_version)}>이전 이력 더 보기</button>}
    </>}
  </section>;
}
