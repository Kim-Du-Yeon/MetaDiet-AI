import {useCallback, useEffect, useRef, useState} from 'react';
import {getAdminFeedback, getAdminFeedbackDetail, getAdminFeedbackAssignees} from '../api/dietApi';
import FeedbackReview from './FeedbackReview';
import useFeedbackAutoRefresh from './useFeedbackAutoRefresh';
import {feedbackStatuses, feedbackCategories, feedbackDate} from './feedbackOptions';
import './AdminFeedback.css';

export default function AdminFeedback() {
  const [status,setStatus]=useState(''), [category,setCategory]=useState(''), [offset,setOffset]=useState(0);
  const [assignee,setAssignee]=useState(''), [assignees,setAssignees]=useState(null), [assigneeError,setAssigneeError]=useState('');
  const [assigneeRetry,setAssigneeRetry]=useState(0);
  const [autoRefresh,setAutoRefresh]=useState(true), [lastRefresh,setLastRefresh]=useState(null);
  const refresh=useCallback(()=>setReload(n=>n+1),[]);
  const [reload,setReload]=useState(0), [data,setData]=useState(undefined), [error,setError]=useState('');
  const [busy,setBusy]=useState(true), [selected,setSelected]=useState(null);
  const [detail,setDetail]=useState(null), [detailError,setDetailError]=useState(''), [detailReload,setDetailReload]=useState(0);
  const reviewGeneration=useRef(0);
  const generation=reviewGeneration.current;
  const choose=useCallback(id=>{reviewGeneration.current+=1;setSelected(id);},[]);
  useEffect(()=>()=>{reviewGeneration.current+=1;},[]);
  useEffect(()=>{
    let active=true; setBusy(true); setError('');
    getAdminFeedback({status,category,assignee,offset}).then(result=>{if(active){setData(result);if(result)setLastRefresh(new Date());}})
      .catch(reason=>{if(active)setError(reason.message);}).finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;};
  },[status,category,assignee,offset,reload]);
  const authorized=Boolean(data);
  useFeedbackAutoRefresh(autoRefresh&&authorized,busy,refresh);
  useEffect(()=>{
    if(!authorized)return;
    let active=true;setAssigneeError('');
    getAdminFeedbackAssignees().then(result=>{if(active)setAssignees(result?.items||[]);})
      .catch(reason=>{if(active)setAssigneeError(reason.message);});
    return()=>{active=false;};
  },[authorized,assigneeRetry]);
  useEffect(()=>{
    let active=true; setDetail(null); setDetailError('');
    if(selected) getAdminFeedbackDetail(selected).then(result=>{
      if(active) {if(result)setDetail(result);else {choose(null);setData(null);}}
    }).catch(reason=>{if(active)setDetailError(reason.message);});
    return()=>{active=false;};
  },[selected,detailReload,choose]);
  if(data===null)return null;
  const filter = setter => e=>{setter(e.target.value);setOffset(0);choose(null);};
  return <section className="settings-card admin-feedback" aria-labelledby="admin-feedback-title">
    <p className="settings-eyebrow">BETA FEEDBACK MANAGEMENT</p>
    <h2 id="admin-feedback-title">피드백 관리</h2>
    <p>관리자 전용 · 의견을 검토하고 처리 상태를 관리합니다.</p>
    <div className="feedback-review__actions">
      <label className="feedback-auto-refresh"><input type="checkbox" checked={autoRefresh} onChange={event=>setAutoRefresh(event.target.checked)}/>목록 자동 갱신</label>
      <small>{autoRefresh?'30초 간격 · 숨긴 탭은 일시 중지':'자동 갱신 중지'}{lastRefresh?` · 최근 성공: ${feedbackDate(lastRefresh)}`:''}</small>
    </div>
    <small>목록·건수만 갱신하며 상세 편집은 유지합니다. 상세는 ‘최신 내용 다시 불러오기’로 갱신하세요.</small>
    {!busy && !error && data?.counts && <div className="feedback-counts" role="status" aria-label="피드백 건수">
      <strong>전체 미처리 {data.counts.total_unprocessed}건</strong>
      <strong>선택 담당자·종류 미처리 {data.counts.unprocessed}건</strong>
      <span>현재 조건 {data.counts.matched_total}건</span>
      <strong>전체 오래된 미처리 {data.counts.total_stale ?? 0}건</strong>
      <strong>선택 범위 오래된 미처리 {data.counts.stale ?? 0}건</strong>
    </div>}
    <small>미처리: 접수·재현 중·보류 · 수정 완료·재검증 완료 제외. 미처리 집계는 상태 필터와 무관하며 목록 새로고침·처리 저장 시 갱신됩니다.</small>
    <p className="feedback-age-help">오래된 미처리: 접수 후 7일(168시간) 이상 경과한 미처리 건 · 메모나 담당자를 변경해도 접수일은 유지됩니다.</p>
    <div className="feedback-review__actions">
      <label>담당자 필터<select aria-label="담당자 필터" value={assignee} onChange={filter(setAssignee)} disabled={busy}>
        <option value="">전체 담당자</option><option value="unassigned">미지정</option>
        {assignees?.map(row=><option value={row.id} key={row.id}>{row.email}</option>)}
      </select></label>
      <label>피드백 상태 필터<select value={status} onChange={filter(setStatus)} disabled={busy}>
        <option value="">전체 상태</option>{Object.entries(feedbackStatuses).map(([v,l])=><option value={v} key={v}>{l}</option>)}
      </select></label>
      <label>피드백 종류 필터<select value={category} onChange={filter(setCategory)} disabled={busy}>
        <option value="">전체 종류</option>{Object.entries(feedbackCategories).map(([v,l])=><option value={v} key={v}>{l}</option>)}
      </select></label>
      <button type="button" disabled={busy} onClick={()=>setReload(n=>n+1)}>목록 새로고침</button>
    </div>
    {assigneeError && <p role="alert">{assigneeError} <button type="button" onClick={()=>setAssigneeRetry(n=>n+1)}>필터 담당자 다시 시도</button></p>}
    {busy && <p role="status">피드백을 불러오는 중입니다.</p>}
    {error && <p role="alert">{error}</p>}
    {!busy && !error && data?.items.length===0 && <p>조건에 맞는 피드백이 없습니다.</p>}
    {!error && <ul className="admin-feedback__list">{data?.items.map(row=><li key={row.id}>
      <button type="button" aria-pressed={selected===row.id} disabled={busy||selected===row.id} onClick={()=>choose(row.id)}>
        <strong>{feedbackCategories[row.category]} · {row.rating}점 · {feedbackStatuses[row.status]}</strong>
        {row.is_stale && <strong className="feedback-stale">7일 이상 미처리</strong>}
        <span>{row.preview || '작성된 의견 없음'}</span><small>{feedbackDate(row.created_at)} · 담당자: {row.assignee_id?(assignees?.find(person=>person.id===row.assignee_id)?.email||'기존 관리자'):'미지정'}</small>
      </button></li>)}</ul>}
    <div className="feedback-review__actions" aria-label="피드백 페이지 이동">
      <button type="button" disabled={busy||offset===0} onClick={()=>{setOffset(n=>n-20);choose(null);}}>이전 페이지</button>
      <span>{Math.floor(offset/20)+1}페이지</span>
      <button type="button" disabled={busy||!data?.has_more||!!error} onClick={()=>{setOffset(n=>n+20);choose(null);}}>다음 페이지</button>
    </div>
    {selected && !detail && !detailError && <p role="status">상세 내용을 불러오는 중입니다.</p>}
    {detailError && <div role="alert">{detailError}<button type="button" onClick={()=>setDetailReload(n=>n+1)}>상세 다시 시도</button></div>}
    {detail && <FeedbackReview feedback={detail} onSaved={saved=>{
      if(reviewGeneration.current!==generation)return;
      setDetail(saved);setReload(n=>n+1);
    }} onReload={()=>{reviewGeneration.current+=1;setDetailReload(n=>n+1);}} onClose={()=>choose(null)}/>}
  </section>;
}
