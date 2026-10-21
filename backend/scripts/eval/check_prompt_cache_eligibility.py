"""Count only: eligibility of100 public RAG prefixes and100 bounded synthetic histories.

No cache creation or generation. This is NOT a cache latency/quality comparison.
"""
import asyncio,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT/"backend/.env",override=True)
from app.rag.qa import QA_PROMPT,NO_EVIDENCE
from app.rag.region_guidance import get_region_guidance

async def main():
    load_dotenv(ROOT/'backend/.env',override=True)
    from google import genai
    from app.core.config import get_settings
    folder=ROOT/'docs/prompt_control/comparison'
    summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    label=summary['selection'];report=json.loads((folder/'paired.json').read_text(encoding='utf-8'))
    baseline=[r for r in report['rows'] if r['condition']==label]
    old=ROOT/'docs/agentic_rag/20261021-controlled-hybrid-v14/attempts.jsonl'
    rag=[json.loads(line) for line in old.read_text(encoding='utf-8').splitlines() if json.loads(line)['condition']=='baseline']
    if len(rag)!=100:raise ValueError('Require frozen100 Hybrid artifacts')
    snapshot=report['prompt_snapshots'][label]
    prefixes=[]
    for index,row in enumerate(rag):
        messages=QA_PROMPT.format_messages(context=row['context'],question='',no_evidence=NO_EVIDENCE,region_guidance=get_region_guidance('KR'))
        prefixes.append(('rag',index,messages[0].content))
    for index in range(100):
        history=[{'role':'assistant','content':baseline[(index+j)%100]['answer']} for j in range(10)]
        # Same message count and per-message cap as production DietTeam history.
        text=snapshot['texts']['team.compact_followup']+'\n'+json.dumps([str(m)[:2000] for m in history],ensure_ascii=False)
        prefixes.append(('multiturn',index,text))
    destination=ROOT/'docs/prompt_control/cache-eligibility.json'
    value=json.loads(destination.read_text(encoding='utf-8')) if destination.exists() else {'type':'count_tokens_applicability_only','selected_prompt':label,'model':'gemini-3.8-flash','minimum_tokens':1024,'cache_created':False,'generation_called':False,'personal_data':False,'history_note':'100 synthetic windows from saved benchmark answers;10 messages capped2000characters each; not maximum production history','rows':[]}
    counts={r['prefix_sha256']:r['tokens'] for r in value['rows']};done={(r['kind'],r['index']) for r in value['rows']}
    client=genai.Client(api_key=get_settings().gemini_api_key,http_options={'timeout':10000,'retry_options':{'attempts':1}})
    try:
        for kind,index,text in prefixes:
            if (kind,index) in done:continue
            digest=hashlib.sha256(text.encode()).hexdigest()
            if digest not in counts:counts[digest]=(await client.aio.models.count_tokens(model='gemini-3.8-flash',contents=text)).total_tokens
            value['rows'].append({'kind':kind,'index':index,'prefix_sha256':digest,'tokens':counts[digest],'minimum_met':counts[digest]>=1024})
            destination.write_text(json.dumps(value,indent=2),encoding='utf-8')
        value['summary']={kind:{'attempts':100,'minimum_met':sum(r['minimum_met'] for r in value['rows'] if r['kind']==kind),'maximum_tokens':max(r['tokens'] for r in value['rows'] if r['kind']==kind)} for kind in ['rag','multiturn']}
        value['decision']='No production explicit caching without demonstrated natural reuse and total-cost advantage over implicit-enabled ordinary calls; no padding.'
        destination.write_text(json.dumps(value,indent=2),encoding='utf-8');print(json.dumps(value['summary']))
    finally:await client.aio.aclose();client.close()
if __name__=='__main__':asyncio.run(main())
