"""Matched ordinary(implicit-enabled) vs explicit public-RAG prefix benchmark.

Frozen100 saved retrieval contexts, grouped exact prefixes, AB/BA, one worker.
No DB or retrieval/embedding calls. Usage-backed streaming TTFT and total latency.
"""
import argparse,asyncio,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT/'backend/.env',override=True)
os.environ.update(LANGSMITH_TRACING='true',LANGSMITH_HIDE_INPUTS='true',LANGSMITH_HIDE_OUTPUTS='true',LANGSMITH_PROJECT='metadiet-cache-rag-20261022')
from google import genai
from langchain_core.messages import message_chunk_to_message
from app.core.config import get_settings
from app.core.llm import get_chat_model,response_text
from app.core.gemini_cache import CachePool,GeminiCacheProvider,invoke_cached
from app.core.prompt_release_control import validate_snapshot,using_snapshot
from app.core.prompt_service import approval_key
from app.rag.qa import QA_PROMPT,NO_EVIDENCE
from app.rag.region_guidance import get_region_guidance
from scripts.eval import eval_budget
from scripts.eval.cache_eval_budget import CacheAccounting,install_cache_guard
from scripts.eval.model_routing_support import estimate_cost

from scripts.eval.cache_artifacts import save_json as save

def frozen_cases():
    folder=ROOT/'docs/agentic_rag/20261021-controlled-hybrid-v14'
    by_id={c['attempt_id']:c for c in json.loads((folder/'cases.json').read_text(encoding='utf-8'))}
    rows=[json.loads(line) for line in (folder/'attempts.jsonl').read_text(encoding='utf-8').splitlines() if json.loads(line)['condition']=='baseline']
    result=[]
    for row in rows:
        case=by_id[row['attempt_id']]
        prefix=QA_PROMPT.format_messages(context=row['context'],question='',no_evidence=NO_EVIDENCE,region_guidance=get_region_guidance('KR'))[0].content
        result.append({**case,'prefix':prefix,'prefix_sha256':hashlib.sha256(prefix.encode()).hexdigest(),'context':row['context']})
    result.sort(key=lambda c:(c['prefix_sha256'],c['attempt_id']))
    if len(result)!=100 or len({c['attempt_id'] for c in result})!=100:raise ValueError('Require frozen100 cases')
    return result

async def main(limit):
    folder=ROOT/'docs/prompt_control/cache-rag';folder.mkdir(parents=True,exist_ok=True)
    cases=frozen_cases();frozen=json.dumps(cases,ensure_ascii=False,indent=2)+'\n';path=folder/'frozen.json'
    if path.exists() and path.read_text(encoding='utf-8')!=frozen:raise ValueError('Frozen cohort changed')
    path.write_text(frozen,encoding='utf-8',newline='\n')
    protocol=json.loads((ROOT/'docs/prompt_control/budget-protocol.json').read_text());eval_budget.TOTAL=protocol['total_limit_usd'];eval_budget.LIMITS=protocol['stage_caps']
    budget=eval_budget.Budget(protocol['ledger']);account=CacheAccounting();install_cache_guard(budget,'comparison',account)
    settings=get_settings();settings.model_max_retries=0
    snapshot=validate_snapshot(json.loads((ROOT/'docs/prompt_control/approved-release.json').read_text(encoding='utf-8')),approval_key())
    client=genai.Client(api_key=settings.gemini_api_key,http_options={'timeout':10000,'retry_options':{'attempts':1}})
    provider=GeminiCacheProvider(client);pool=CachePool(provider.create,provider.delete,secret=os.urandom(32),ttl=300)
    model=get_chat_model(model_name='gemini-3.8-flash',temperature=0,max_tokens=1024,thinking_level='low',reuse_provider=True);model.prepare()
    target=folder/'paired.json'
    report=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'scope':'synthetic public RAG generation boundary, frozen retrieval, not actual users/full Agent service latency','cases_sha256':hashlib.sha256(frozen.encode()).hexdigest(),'prompt_snapshot':snapshot.wire,'model':'gemini-3.8-flash','temperature':0,'thinking':'low','output_cap':1024,'workers':1,'order':'grouped exact prefixes then attemptID; AB/BA within case; same stateless SDK client both conditions','baseline':'ordinary API with implicit caching enabled; not cache-off','ttl_seconds':300,'minimum_tokens_server':1024,'creation_cost_note':'conservative full-price input-write upper + full TTL storage, not verified separate creation charge/invoice','cache_gate':'quality within2pp; failure noninferior; p95<=1.1x; total upper estimate>=10percent lower; complete usage; freshness/isolation100offline; private runtime remainsoff','rows':[],'cache_creations':[]}
    for row in report['rows']:
        if row['status']=='running':row.update(status='interrupted_unknown',ms=0,ttft_ms=None,model_cost_usd=None,cache_overhead_upper_usd=0)
    done={(r['case_id'],r['condition']) for r in report['rows']}
    try:
      for index,case in enumerate(cases[:limit]):
       for label in (['ordinary','explicit'] if index%2==0 else ['explicit','ordinary']):
        if (case['attempt_id'],label) in done:continue
        started=time.perf_counter();first=None;event_index=len(account.events)
        key=pool.key('gemini-3.8-flash',snapshot.digest,case['prefix'],None)
        cache_stage='reuse' if key in pool.entries and pool.entries[key]['expires']>pool.clock() else 'first'
        row={'case_id':case['attempt_id'],'condition':label,'status':'running','cache_stage':cache_stage if label=='explicit' else 'ordinary','prefix_sha256':case['prefix_sha256']}
        report["rows"].append(row);save(target,report)
        async def invoke(messages,**kwargs):
            nonlocal first
            aggregate=None
            async for chunk in model.astream(messages,config={'metadata':{'prompt_experiment_id':'cache-rag-20261022','prompt_experiment_group':label,'case_id':case['attempt_id'],'prefix_sha256':case['prefix_sha256']}},**kwargs):
                if first is None and response_text(chunk).strip():first=(time.perf_counter()-started)*1000
                aggregate=chunk if aggregate is None else aggregate+chunk
            if aggregate is None:raise ValueError('Empty stream')
            return message_chunk_to_message(aggregate)
        try:
            with using_snapshot(snapshot):
                messages=[{'role':'user','content':case['question']}]
                if label=='explicit':answer=await asyncio.wait_for(invoke_cached(pool,invoke,'gemini-3.8-flash',snapshot.digest,case['prefix'],messages,eligible=True),65)
                else:answer=await asyncio.wait_for(invoke([{'role':'system','content':case['prefix']},*messages]),65)
            usage=answer.usage_metadata or {};finish=str(answer.response_metadata.get('finish_reason',''))
            row.update(status='completed' if finish=='STOP' else 'truncated_or_nonstop',answer=response_text(answer),usage=usage,finish_reason=finish,model_cost_usd=estimate_cost('gemini-3.8-flash',usage),cached_input_tokens=(usage.get('input_token_details') or {}).get('cache_read',0))
        except Exception as exc:
            row['status']='failed'
            row['error']={'type':type(exc).__name__,'code':getattr(exc,'code',None)}
        row.update(ms=(time.perf_counter()-started)*1000,ttft_ms=first,creation_events=account.events[event_index:])
        row['cache_overhead_upper_usd']=sum(e['creation_input_upper_usd']+e['storage_full_ttl_upper_usd'] for e in row['creation_events'])
        report['cache_creations'].extend(row['creation_events']);save(target,report)
        print(case['attempt_id'],label,row['status'],round(row['ms']),row.get('cached_input_tokens'),flush=True)
    finally:
      await pool.close();await client.aio.aclose();client.close()
      from app.core.llm import close_shared_model_client
      await close_shared_model_client()
    print('paired attempts',len(report['rows']),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--allow-paid',action='store_true');parser.add_argument('--limit',type=int,default=100);args=parser.parse_args()
    if not args.allow_paid:parser.error('Offline default; paid authorization required')
    if not 1<=args.limit<=100:parser.error('Limit1..100')
    asyncio.run(main(args.limit))
