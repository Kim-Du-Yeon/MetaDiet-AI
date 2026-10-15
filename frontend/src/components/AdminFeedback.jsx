import {useCallback, useEffect, useRef, useState} from 'react';
import {getAdminFeedback, getAdminFeedbackDetail} from '../api/dietApi';
import FeedbackReview from './FeedbackReview';
import {feedbackStatuses, feedbackCategories, feedbackDate} from './feedbackOptions';
import './AdminFeedback.css';

export default function AdminFeedback() {
  const [status,setStatus]=useState(''), [category,setCategory]=useState(''), [offset,setOffset]=useState(0);
  const [reload,setReload]=useState(0), [data,setData]=useState(undefined), [error,setError]=useState('');
  const [busy,setBusy]=useState(true), [selected,setSelected]=useState(null);
  const [detail,setDetail]=useState(null), [detailError,setDetailError]=useState(''), [detailReload,setDetailReload]=useState(0);
  const reviewGeneration=useRef(0);
  const generation=reviewGeneration.current;
  const choose=useCallback(id=>{reviewGeneration.current+=1;setSelected(id);},[]);
  useEffect(()=>()=>{reviewGeneration.current+=1;},[]);
  useEffect(()=>{
    let active=true; setBusy(true); setError('');
    getAdminFeedback({status,category,offset}).then(result=>{if(active)setData(result);})
      .catch(reason=>{if(active)setError(reason.message);}).finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;};
  },[status,category,offset,reload]);
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
      <label>피드백 상태 필터<select value={status} onChange={filter(setStatus)} disabled={busy}>
        <option value="">전체 상태</option>{Object.entries(feedbackStatuses).map(([v,l])=><option value={v} key={v}>{l}</option>)}
      </select></label>
      <label>피드백 종류 필터<select value={category} onChange={filter(setCategory)} disabled={busy}>
        <option value="">전체 종류</option>{Object.entries(feedbackCategories).map(([v,l])=><option value={v} key={v}>{l}</option>)}
      </select></label>
      <button type="button" disabled={busy} onClick={()=>setReload(n=>n+1)}>목록 새로고침</button>
    </div>
    {busy && <p role="status">피드백을 불러오는 중입니다.</p>}
    {error && <p role="alert">{error}</p>}
    {!busy && !error && data?.items.length===0 && <p>조건에 맞는 피드백이 없습니다.</p>}
    {!error && <ul className="admin-feedback__list">{data?.items.map(row=><li key={row.id}>
      <button type="button" aria-pressed={selected===row.id} disabled={busy||selected===row.id} onClick={()=>choose(row.id)}>
        <strong>{feedbackCategories[row.category]} · {row.rating}점 · {feedbackStatuses[row.status]}</strong>
        <span>{row.preview || '작성된 의견 없음'}</span><small>{feedbackDate(row.created_at)}</small>
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
