"""Publish sanitized saved experiment metrics to LangSmith, without model calls.

These are POSTHOC IMPORTS, not reconstructed native provider traces. Native span
latency is not the measured model latency; measured_ms and raw artifacts govern.
"""
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
from uuid import NAMESPACE_URL,uuid5
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from dotenv import load_dotenv
from app.core.langsmith_prompts import make_client

def verify_sources(folder,summary):
    for name,expected in summary["source_hashes"].items():
        if Path(name).name!=name or hashlib.sha256((folder/name).read_bytes()).hexdigest()!=expected:
            raise ValueError("Frozen import artifact changed")

def main():
    load_dotenv(ROOT/'backend/.env',override=True)
    folder=ROOT/'docs/prompt_control/comparison';summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    if not summary['judge_usage_complete']:raise ValueError('Incomplete evaluation')
    verify_sources(folder,summary)
    report=json.loads((folder/'paired.json').read_text(encoding='utf-8'));judges=json.loads((folder/'judges.json').read_text(encoding='utf-8'))
    cases=json.loads((folder/'frozen.json').read_text(encoding='utf-8'))
    grades={(r['case_id'],label):r['grades'][position] for r in judges['rows'] for position,label in r['mapping'].items()}
    path=ROOT/'docs/prompt_control/langsmith-import.json'
    output=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'type':'posthoc_sanitized_metric_import_not_native_model_traces','dataset_name':'metadiet-prompts-frozen100-20261021','projects':{},'runs':[]}
    client=make_client(timeout_ms=10000)
    from langsmith.utils import LangSmithNotFoundError
    try:
        try:dataset=client.read_dataset(dataset_name=output['dataset_name'])
        except LangSmithNotFoundError:dataset=client.create_dataset(output['dataset_name'],description='Frozen synthetic100 IDs/expected numbers; no actual user data')
        examples=list(client.list_examples(dataset_id=dataset.id,limit=100))
        present={e.inputs['case_id'] for e in examples}
        missing=[{'id':str(uuid5(NAMESPACE_URL,'metadiet-prompts-example-'+c['id'])),'inputs':{'case_id':c['id']},'outputs':{'expected_calories':c['calories'],'expected_target':c['target']},'metadata':{'synthetic':True,'cases_sha256':report['cases_sha256']}} for c in cases if c['id'] not in present]
        if missing:client.create_examples(dataset_id=dataset.id,examples=missing)
        ids={e.inputs['case_id']:e.id for e in client.list_examples(dataset_id=dataset.id,limit=100)}
        for label in ['v1','v2']:
            name='metadiet-prompts-'+label+'-20261021'
            project=client.create_project(name,upsert=True,reference_dataset_id=dataset.id,description='POSTHOC saved-result import; measured_ms metadata is authoritative, native span latency is import overhead',metadata={'prompt_experiment_id':'prompt-control-20261021','prompt_experiment_group':label,'synthetic':True,'posthoc_import':True})
            output['projects'][label]={'name':name,'id':str(project.id)}
            existing={str(r.id) for r in client.list_runs(project_name=name,limit=100,select=['id'])}
            done={r['id'] for r in output['runs']}
            for row in report['rows']:
                if row['condition']!=label:continue
                identity=str(uuid5(NAMESPACE_URL,'metadiet-prompts-'+label+'-'+row['case_id']))
                if identity in done:continue
                grade=grades[(row['case_id'],label)];now=datetime.now(timezone.utc)
                metadata={**row['prompt_metadata'],'prompt_experiment_id':'prompt-control-20261021','prompt_experiment_group':label,'posthoc_import':True,'case_id':row['case_id'],'model':row['model'],'measured_ms':row['ms'],'estimated_cost_usd':row['cost_usd'],'input_tokens':sum(u['input_tokens'] for u in row['usage']),'output_tokens':sum(u['output_tokens'] for u in row['usage']),'artifact_sha256':summary['source_hashes']['paired.json']}
                if identity not in existing:client.create_run('saved-synthetic-coaching-result',{'case_id':row['case_id']},'chain',id=identity,project_name=name,reference_example_id=ids[row['case_id']],start_time=now,end_time=now,extra={'metadata':metadata},outputs={'synthetic':True})
                client.create_feedback(identity,'synthetic_quality',score=int(grade['correct'] and grade['faithful'] and row['fresh'] and row['no_write']),feedback_id=uuid5(NAMESPACE_URL,identity+'-quality'),source_info={'rubric_sha256':judges['rubric_sha256'],'judge':'gemini-3.1-pro-preview','posthoc_import':True},stop_after_attempt=1)
                output['runs'].append({'id':identity,'case_id':row['case_id'],'group':label})
                path.write_text(json.dumps(output,indent=2),encoding='utf-8')
            print(label,'imported100',flush=True)
    finally:client.close()
if __name__=='__main__':main()
