"""Functional synthetic development probes, never a performance benchmark."""
import argparse,asyncio,hashlib,importlib.machinery,importlib.util,json,sys,time
from pathlib import Path
from benchmark_agentic_rag import ROOT,Usage,safe_error

async def main(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    from app.rag import agentic,qa
    qa._llm.max_tokens=2048
    from app.core.config import get_settings
    from langchain_core.documents import Document
    directory=Path(args.directory); output=directory/'attempts.jsonl'
    if output.exists(): raise ValueError('Refuse overwrite existing development outputs')
    cases=json.loads((directory/'cases.json').read_text(encoding='utf-8'))
    loader=importlib.machinery.SourceFileLoader('development_frozen_baseline',args.baseline_source)
    spec=importlib.util.spec_from_loader(loader.name,loader); old=importlib.util.module_from_spec(spec)
    sys.modules[loader.name]=old;loader.exec_module(old)
    settings=get_settings()
    settings.rag_chunks_path=str((ROOT/'backend'/settings.rag_chunks_path).resolve())
    async def run_case(index,case):
        for condition in (['baseline','agentic'] if index%2==0 else ['agentic','baseline']):
            row={'attempt_id':case['attempt_id'],'condition':condition,'status':'failed','purpose':'synthetic_functionality_only'}
            model=old if condition=='baseline' else agentic
            usage=Usage(); decisions=[]; queries=[]; start=time.perf_counter()
            async def retrieve(q,**kw):
                queries.append(q)
                research=len(queries)>1
                content=case.get('research_context',case['context']) if research else case['context']
                metadata={'source_file':case['source'],'page':case['page']+(100 if research else 0)}
                if case.get('population'):metadata['population']=case['population']
                metadata['document_sha256']='synthetic-'+case['attempt_id']
                return {'grounded':True,'max_score':.9,'docs':[Document(page_content=content,metadata=metadata)]}
            async def assess(q,result):
                decision=await model.model_assessment(q,result,config={'callbacks':[usage]})
                decisions.append(decision.model_dump())
                return decision
            try:
                if case.get('neighbor_context') and condition=='agentic':
                    from app.rag.neighbors import NeighborIndex
                    corpus=[Document(page_content=text,metadata={'source_file':case['source'],'page':case['page'],
                            'document_sha256':'synthetic-'+case['attempt_id'],
                            **({'population':case['population']} if case.get('population') else {})})
                            for text in (case['context'],case['neighbor_context'])]
                    async def expand(anchors,q):return NeighborIndex(corpus).expand(anchors,q)
                    result=await model.bounded_retrieve(case['question'],retrieve=retrieve,assess=assess,expand=expand)
                else:
                    result=await model.bounded_retrieve(case['question'],retrieve=retrieve,assess=assess)
                provider_reason=(result.get('agentic') or {}).get('provider_failure_reason')
                if provider_reason in {'credits','auth'}:
                    raise RuntimeError('402 credits depleted' if provider_reason=='credits' else '401 provider authentication unavailable')
                answer=await qa.answer_from_knowledge(case['question'],retrieval_result=result,config={'callbacks':[usage]})
                row.update(status='completed',answer=answer['answer'],context=answer['context'],agentic=result['agentic'],
                           sufficient=result['grounded'],expected_sufficient=case['expected_sufficient'],
                           assessment_contract_pass=result['grounded']==case['expected_sufficient'],
                           expected_rounds=case.get("expected_rounds"),
                           flow_contract_pass=result["grounded"]==case["expected_sufficient"] and (case.get("expected_rounds") is None or result["agentic"]["rounds"]==case["expected_rounds"]))
            except Exception as exc:
                row['error']=safe_error(exc)
            row.update(ms=(time.perf_counter()-start)*1000,usage=usage.calls,decisions=decisions,queries=queries)
            with output.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
            print(json.dumps({k:row.get(k) for k in ('attempt_id','condition','status','assessment_contract_pass','error')}),flush=True)
            if row.get('error',{}).get('reason') in {'credits','quota','auth'}:
                raise RuntimeError('Development provider precondition failed; stop without resampling')
            await asyncio.sleep(1)

    semaphore=asyncio.Semaphore(args.workers)
    async def bounded_case(index,case):
        async with semaphore:
            await run_case(index,case)
    await asyncio.gather(*(bounded_case(index,case) for index,case in enumerate(cases)))

if __name__=='__main__':
    from eval_budget import add_budget_args, activate_budget
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--baseline-source',required=True);p.add_argument('--workers',type=int,choices=(1,2,3),default=1)
    add_budget_args(p)
    args=p.parse_args()
    activate_budget(args,'development')
    try:asyncio.run(main(args))
    except Exception as exc:
        print(json.dumps(safe_error(exc)));raise SystemExit(1)
