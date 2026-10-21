"""Functional synthetic development probes, never a performance benchmark."""
import argparse,asyncio,hashlib,importlib.machinery,importlib.util,json,sys,time
from pathlib import Path
from benchmark_agentic_rag import ROOT,Usage,safe_error

async def main(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    from app.rag import agentic,qa
    from app.core.config import get_settings
    from langchain_core.documents import Document
    directory=Path(args.directory); output=directory/'attempts.jsonl'
    if output.exists(): raise ValueError('Refuse overwrite existing development outputs')
    cases=json.loads((directory/'cases.json').read_text(encoding='utf-8'))
    loader=importlib.machinery.SourceFileLoader('development_frozen_baseline',args.baseline_source)
    spec=importlib.util.spec_from_loader(loader.name,loader); old=importlib.util.module_from_spec(spec)
    sys.modules[loader.name]=old;loader.exec_module(old)
    settings=get_settings()
    for index,case in enumerate(cases):
        for condition in (['baseline','agentic'] if index%2==0 else ['agentic','baseline']):
            row={'attempt_id':case['attempt_id'],'condition':condition,'status':'failed','purpose':'synthetic_functionality_only'}
            model=old if condition=='baseline' else agentic
            usage=Usage(); start=time.perf_counter()
            async def retrieve(q,**kw):
                return {'grounded':True,'max_score':.9,'docs':[Document(page_content=case['context'],metadata={'source_file':case['source'],'page':case['page']})]}
            async def assess(q,result):
                return await model.model_assessment(q,result,config={'callbacks':[usage]})
            try:
                result=await model.bounded_retrieve(case['question'],retrieve=retrieve,assess=assess)
                answer=await qa.answer_from_knowledge(case['question'],retrieval_result=result,config={'callbacks':[usage]})
                row.update(status='completed',answer=answer['answer'],context=answer['context'],agentic=result['agentic'],
                           sufficient=result['grounded'],expected_sufficient=case['expected_sufficient'],
                           assessment_contract_pass=result['grounded']==case['expected_sufficient'])
            except Exception as exc:
                row['error']=safe_error(exc)
            row.update(ms=(time.perf_counter()-start)*1000,usage=usage.calls)
            with output.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
            print(json.dumps({k:row.get(k) for k in ('attempt_id','condition','status','assessment_contract_pass','error')}),flush=True)
            if row.get('error',{}).get('reason') in {'credits','quota'}:
                raise RuntimeError('Development provider precondition failed; stop without resampling')
            await asyncio.sleep(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--baseline-source',required=True)
    try:asyncio.run(main(p.parse_args()))
    except Exception as exc:
        print(json.dumps(safe_error(exc)));raise SystemExit(1)
