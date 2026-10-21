"""Sign frozen evaluated static release and publish PRIVATE manifest; never promote."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from dotenv import load_dotenv
from app.core.prompt_release_control import _snapshot,sign_snapshot
from app.core.langsmith_prompts import make_client,LangSmithReleaseReader,RELEASE_REPO

def approved_selection(summary):
    label=summary['selection']
    if not summary.get('judge_usage_complete'):raise ValueError('Judge usage incomplete')
    for group in summary['summary'].values():
        if group['attempts']!=100 or not group['judge_complete'] or not group['usage_complete']:raise ValueError('Incomplete comparison')
    selected=summary['summary'][label]
    if selected['fresh_percent']!=100 or selected['no_write_percent']!=100 or selected['failure_percent']>2:raise ValueError('Safety/freshness gate failed')
    if label=='v2' and not summary['candidate_passed']:raise ValueError('Candidate gate failed')
    return label

def main(alias=None):
    load_dotenv(ROOT/'backend/.env',override=True)
    folder=ROOT/'docs/prompt_control/comparison';path=folder/'summary.json'
    summary=json.loads(path.read_text(encoding='utf-8'));label=approved_selection(summary)
    for name,value in summary['source_hashes'].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=value:raise ValueError('Frozen evaluation source changed')
    from cryptography.hazmat.primitives import serialization
    key=serialization.load_pem_private_key((ROOT/'backend/.env.prompt-signer').read_bytes(),password=None)
    drafts=json.loads((ROOT/'docs/prompt_control/release-drafts/release-drafts.json').read_text(encoding='utf-8'))
    draft=drafts[label]
    if alias:
        draft=json.loads(json.dumps(draft));draft["manifest"]["release"]=alias
    value=sign_snapshot(_snapshot(draft),key,report_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    body={k:value[k] for k in ['kind','manifest','signature']}
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.messages import SystemMessage
    from langsmith.utils import LangSmithConflictError
    client=make_client()
    try:
        record=client.get_prompt(RELEASE_REPO)
        if record is not None and record.is_public is not False:raise ValueError('Refuse public manifest')
        template=ChatPromptTemplate.from_messages([SystemMessage(content=json.dumps(body,ensure_ascii=False))])
        try:client.push_prompt(RELEASE_REPO,object=template,is_public=False,commit_description='Evaluated atomic release '+label+'; promote this manifest, not individual child tags')
        except LangSmithConflictError:pass
        text,commit=LangSmithReleaseReader(client).pull(RELEASE_REPO,'latest',allow_latest=True)
        if json.loads(text)!=body:raise ValueError('Published manifest readback mismatch')
        value['origin_commit']=commit
        destination=ROOT/'docs/prompt_control'/('approved-release-'+alias+'.json' if alias else 'approved-release.json')
        destination.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'selected':label,'release_commit':commit,'promoted':False}))
    finally:client.close()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--alias',help='Metadata-only control drill; exact same evaluated8 child commits')
    main(parser.parse_args().alias)
