"""Four synthetic calls, explicit --live; no application database access."""
import argparse,asyncio,json,os,time
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env', override=True)
os.environ.pop('GOOGLE_API_KEY',None)
from langsmith import tracing_context,traceable
from langchain_core.tracers.langchain import wait_for_all_tracers
from app.core.trace_policy import PolicyClient
from app.core.llm import get_chat_model

async def main(args):
    if not args.live: raise SystemExit('Explicit --live required')
    os.environ['TRACE_DATA_MODE']='synthetic'
    os.environ['TRACE_SYNTHETIC_ONLY']='true'
    stamp=time.strftime('%Y%m%d-%H%M%S'); results=[]
    for mode in ('synthetic','production'):
        project='metadiet-synthetic-trace-'+mode+'-'+stamp
        client=PolicyClient(mode=mode,api_key=os.environ['LANGSMITH_API_KEY'])
        for model_name in ('gemini-3.1-flash-lite','gemini-3.8-flash'):
            root_id=uuid4()
            @traceable(name='trace-smoke')
            async def ask(question):
                response=await get_chat_model(model_name=model_name,max_tokens=128).ainvoke(question)
                return {'answer':response.content}
            with tracing_context(enabled=True,client=client,project_name=project,metadata={'thread_id':'thread-'+root_id.hex[:24]}):
                await ask('합성 검증입니다. 가상 사용자 테스트김의 체중은 73kg입니다. 저장하지 말고 확인이라고만 답하세요.',langsmith_extra={'run_id':root_id})
            wait_for_all_tracers();client.flush();time.sleep(3)
            root=client.read_run(root_id,load_child_runs=True)
            llms=[r for r in root.child_runs or [] if r.run_type=='llm'];assert llms,'No LLM child'
            rows=[]
            for run in llms:
                meta=(run.extra or {}).get('metadata') or {};usage=meta.get('usage_metadata') or {}
                assert usage.get('total_tokens',0)>0,'Usage missing'
                assert usage.get('total_cost',0)>0,'Cost estimate missing'
                rendered=json.dumps([run.inputs,run.outputs,run.extra],ensure_ascii=False,default=str)
                if mode=='production': assert '테스트김' not in rendered and '73kg' not in rendered,'Mask failure'
                else: assert '테스트김' in json.dumps(run.inputs,ensure_ascii=False),'Synthetic input hidden'
                rows.append({'run_id':str(run.id),'model':meta.get('ls_model_name'),'usage':usage,'duration_seconds':(run.end_time-run.start_time).total_seconds(),'cost_basis':meta.get('cost_basis')})
            results.append({'project':project,'mode':mode,'root_run_id':str(root_id),'llms':rows,'url':client.get_run_url(run=root)})
            Path(args.output).parent.mkdir(parents=True,exist_ok=True)
            Path(args.output).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        client.flush()
    print(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--output',required=True)
    asyncio.run(main(parser.parse_args()))
