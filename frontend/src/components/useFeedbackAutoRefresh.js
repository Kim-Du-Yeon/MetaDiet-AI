import {useEffect} from 'react';

export default function useFeedbackAutoRefresh(enabled, busy, refresh) {
  useEffect(()=>{
    if(!enabled||busy)return;
    let requested=false;
    const run=()=>{
      if(requested||document.visibilityState==='hidden')return;
      requested=true;
      refresh();
    };
    const timer=setInterval(run,30000);
    document.addEventListener('visibilitychange',run);
    window.addEventListener('focus',run);
    return()=>{
      clearInterval(timer);
      document.removeEventListener('visibilitychange',run);
      window.removeEventListener('focus',run);
    };
  },[enabled,busy,refresh]);
}
