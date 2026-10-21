import {useEffect,useState} from 'react';
import {adminPromptRequest} from '../api/dietApi';

export default function PromptControl(){
 const [data,setData]=useState(undefined),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let active=true;adminPromptRequest().then(v=>{if(active)setData(v);}).catch(()=>{if(active)setError('프롬프트 상태를 불러오지 못했습니다.');});return()=>{active=false;};},[]);
 async function refresh(){setBusy(true);setError('');try{setData(await adminPromptRequest(true));}catch{setError('릴리스를 확인하지 못했습니다. 마지막 정상 버전을 유지합니다.');}finally{setBusy(false);}}
 if(data===null)return null;
 return <section className="settings-card" aria-labelledby="prompt-control-title">
  <h2 id="prompt-control-title">프롬프트 릴리스</h2>
  {error&&<p role="alert">{error}</p>}
  {data&&<><p>현재 릴리스: <strong>{data.prompt_release}</strong> · {data.prompt_source}</p>
   <p>{data.remote_enabled?'원격 제어 사용':'로컬 버전 사용'} · 실제 사용자 A/B: {data.ab_enabled?'진행':'중지'}</p>
   <p>갱신 주기: {data.refresh_interval_seconds}초 · 진행 중인 요청과 확인 절차에는 기존 버전을 유지합니다.</p>
   {data.last_refresh_error&&<p role="status">원격 확인 실패: 마지막 정상 릴리스 유지</p>}
   <details><summary>실제 사용 프롬프트 커밋 보기</summary><dl>{Object.entries(data.prompt_commit_ids||{}).map(([name,id])=><div key={name}><dt>{name}</dt><dd style={{overflowWrap:'anywhere'}}>{id||'로컬 패키지'}</dd></div>)}</dl></details>
   <button type="button" disabled={busy||!data.remote_enabled} onClick={refresh}>검증된 릴리스 다시 가져오기</button>
  </>}
 </section>;
}
