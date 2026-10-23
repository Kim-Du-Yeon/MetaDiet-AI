"""Offline-only recovery: explicit labelled scores, immutable source evidence."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from scripts.eval.batch_clarification_resume import parse_grade
from scripts.eval.resume_clarification_judging import validate_resume
from scripts.eval.clarification_execution import digest,analyze
from scripts.eval.cache_artifacts import save_json


def failure_kind(value):
    if isinstance(value,dict) and set(value)=={'a','b'} and any(isinstance(value[s],list) for s in ['a','b']):return 'unnamed_grade_arrays'
    if isinstance(value,list):return 'unnamed_root_or_wrapped_arrays'
    if isinstance(value,dict) and any(value.get(side+'_focused_required_question','absent') is None for side in ['a','b']):return 'required_boolean_null'
    return 'other_schema_error'


def recover(source,folder):
    source=Path(source);folder=Path(folder)
    if folder.exists():raise ValueError('Recovery destination exists; never overwrite source/results')
    validate_resume(source)
    original=(source/'judges.json').read_bytes();judges=json.loads(original)
    report=json.loads((source/'paired.json').read_text(encoding='utf-8'));cases=json.loads((source/'frozen.json').read_text(encoding='utf-8'))
    saved_summary=json.loads((source/'summary.json').read_text(encoding='utf-8'))
    hashes={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in ['paired.json','judges.json','frozen.json']}
    if saved_summary['source_hashes']!=hashes:raise ValueError('Source evidence hashes changed')
    updated=copy.deepcopy(judges);changes=[];unresolved=[]
    for row in updated['rows']:
        if row['status']=='completed':continue
        raw_path=source/'raw-grades'/(row['case_id']+'.json');raw=json.loads(raw_path.read_text(encoding='utf-8'))
        if digest(raw)!=row.get('raw_sha256'):raise ValueError('Stored raw grade hash mismatch')
        value=json.loads(raw['text'])
        try:grade=parse_grade(raw['text']).model_dump()
        except ValueError:
            unresolved.append({'case_id':row['case_id'],'reason':failure_kind(value),'raw_sha256':digest(raw),'finish_reasons':raw['finish_reasons'],'automatic_inference_allowed':False})
            continue
        shared=isinstance(value,dict) and 'reason' in value and all(side+'_reason' not in value for side in ['a','b'])
        if not shared:raise ValueError('Unexpected recovery shape; review before accepting')
        prior=copy.deepcopy(row)
        row.pop('error',None);row.update(status='completed',grades=grade,offline_recovery={'method':'complete_explicit_scores_shared_verbatim_rationale','rationale_scope':'shared across a/b, not independent per-side explanations','raw_sha256':digest(raw),'score_pointers':{side:{name:'/'+side+'_'+name for name in grade[side] if name!='reason'} for side in ['a','b']},'rationale_pointer':'/reason','new_model_calls':0})
        changes.append({'case_id':row['case_id'],'original_row':prior,'replacement_sha256':digest(row),'raw_source':str(raw_path.relative_to(ROOT)).replace('\\','/')})
    if (source/'judges.json').read_bytes()!=original:raise ValueError('Source changed during recovery')
    folder.mkdir(parents=True)
    for name in ['paired.json','frozen.json']:(folder/name).write_bytes((source/name).read_bytes())
    save_json(folder/'judges.json',updated);save_json(folder/'recovery-changes.json',changes);save_json(folder/'unresolved.json',unresolved)
    summary=analyze(report,updated,cases)
    summary['source_hashes']={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in ['paired.json','judges.json','frozen.json']};save_json(folder/'summary.json',summary)
    batch_completed=[r for r in updated['rows'] if r['status']=='completed' and r.get('transport')=='batch']
    observed_mean=sum(r['batch_cost_usd'] for r in batch_completed)/len(batch_completed)
    result={'source_hashes':hashes,'source_valid_pairs':sum(r['status']=='completed' for r in judges['rows']),'source_failed_pairs':sum(r['status']!='completed' for r in judges['rows']),'recovered_pairs':len(changes),'valid_pairs':sum(r['status']=='completed' for r in updated['rows']),'remaining_pairs':len(unresolved),'failure_groups':{key:sum(r['reason']==key for r in unresolved) for key in sorted({r['reason'] for r in unresolved})},'paid_calls':0,'changed_scores':0,'rubric_changed':False,'existing_completed_grades_changed':False,'source_files_changed':False,'candidate_approved':False,'remaining_batch_cost_estimate_usd':observed_mean*len(unresolved),'estimate_basis':'Mean observed valid prior Batch cost; new generation length and thinking usage can differ. Not a quote or new authorization.','recommended_additional_cap_usd':.25,'recommended_initial_smoke_pairs':2,'cost_is_not_reserved_or_spent':True,'next_step':'Do not infer array positions or replace null booleans. Paid regrading needs approval after reviewing estimate. Use stored answers only.','implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save_json(folder/'analysis.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',default=str(ROOT/'docs/prompt_control/clarification-balanced/execution-v2/resume-batch'));p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(recover(a.source,a.output)))
