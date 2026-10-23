"""Fail-closed v5 development approval; previous v4 evidence is never rewritten."""
import hashlib,math
from pathlib import Path
from app.core.prompt_release_control import digest
from scripts.eval.clarification_v5 import (ROOT,BASE,SUITE,CONDITIONS,read,sha,validate,candidate_snapshot,reuse_regression)


def cohort_sha(cases):return digest(cases)


def supported(candidate):
    expected=candidate_snapshot(candidate['baseline'])
    if candidate['snapshot']['texts']!=expected['texts']:raise ValueError('Only frozen closing-rule addition supported')
    for n,e in candidate['baseline']['manifest']['prompts'].items():
        if n not in {'team.base','team.compact_followup'} and candidate['snapshot']['manifest']['prompts'][n]!=e:raise ValueError('Unchanged six templates differ')


def verify(candidate,folder,key):
    """Recompute the gate and bindings, never sign an asserted summary flag."""
    from scripts.prompt_release_workflow import validate_candidate,identity
    from scripts.eval import run_clarification_v5 as runner
    from scripts.eval.clarification_execution import request_spec,price_usage
    from scripts.eval.clarification_cases import request_key
    from scripts.eval.clarification_v3 import fixture_truth,format_system,parse_grades
    from app.core.prompt_release_control import _snapshot
    from scripts.eval.run_clarification_comparison import versions
    if versions()!=CONDITIONS['packages']:raise ValueError('Evaluation package environment changed')
    validate_candidate(candidate,key);supported(candidate);folder=Path(folder);p=validate(folder)
    if read(folder/'candidate.json')!=candidate:raise ValueError('Approval candidate differs from evaluated exact commits')
    if identity(candidate['baseline'])!=identity(read(BASE/'approved.json')):raise ValueError('Historical v4 baseline changed')
    r=read(folder/'main/answers.json');j=read(folder/'main/judges.json');cs=read(folder/'frozen.json');by={c['id']:c for c in cs}
    if r['experiment']!=SUITE or r['conditions']!=CONDITIONS or r['cases_sha256']!=cohort_sha(cs) or r['protocol_sha256']!=digest(p) or r['runner_sha256']!=runner.runner_sha():raise ValueError('Execution identity changed')
    if identity(r['snapshots']['v4'])!=identity(candidate['baseline']) or identity(r['snapshots']['v5'])!=identity(candidate['snapshot']):raise ValueError('Evaluated snapshot mismatch')
    expected={(c['id'],l) for c in cs for l in ['v4','v5']};keys=[(a['case_id'],a['condition']) for a in r['rows']]
    if len(keys)!=200 or set(keys)!=expected:raise ValueError('Require200 unique attempts')
    from scripts.eval.v5_evidence_contract import bounded_costs,trace_templates
    bounds=bounded_costs(folder,r['rows'])
    coverage={l:{n:0 for n in ['team.base','team.compact_followup']} for l in ['v4','v5']}
    for a in r['rows']:
        snap=r['snapshots'][a['condition']];meta=_snapshot(snap).metadata();c=by[a['case_id']]
        if a['input_key']!=request_key(c,request_spec(snap)) or any(a['prompt_metadata'].get(k)!=meta[k] for k in ['prompt_commit_ids','prompt_hashes','prompt_bundle_sha256']):raise ValueError('Per-attempt binding changed')
        baseline_failure=a['condition']=='v4' and a['status'] in {'failed','blocked'}
        if not baseline_failure and (a['status']!='completed' or a['no_write'] is not True or not a['answer']):raise ValueError('Incomplete/unsafe candidate serving attempt')
        if a['model']!=CONDITIONS['model'] or type(a['ms']) not in (int,float) or not math.isfinite(a['ms']) or a['ms']<0:raise ValueError('Invalid execution identity/duration')
        if a['cost_usd'] is None:
            if not baseline_failure or a['case_id'] not in bounds:raise ValueError('Unaccounted unknown cost')
        elif type(a['cost_usd']) not in (int,float) or not math.isfinite(a['cost_usd']) or abs(a['cost_usd']-price_usage(CONDITIONS['model'],a['usage']))>1e-9:raise ValueError('Invalid measured cost')
        if a.get('reused_from'):
            if a!=reuse_regression(c,snap):raise ValueError('Reused regression differs from original')
            continue
        trace=read(folder/'main/model-inputs'/(a['case_id']+'-'+a['condition']+'.json'))
        if trace['input_key']!=a['input_key'] or trace['fixture_truth']!=fixture_truth(c):raise ValueError('Trace input/fixture mismatch')
        used=trace_templates(trace['model_inputs'],a['condition'],r['snapshots'],c['question'])
        for n in used:coverage[a['condition']][n]+=1
    if any(n<10 for c in coverage.values() for n in c.values()):raise ValueError('Two-template execution coverage incomplete')
    ids=[g['case_id'] for g in j['rows']]
    if len(ids)!=100 or set(ids)!=set(by):raise ValueError('Missing/duplicate grades')
    answers={(a['case_id'],a['condition']):a['answer'] for a in r['rows']};system=format_system(2)
    for i,c in enumerate(cs):
        g=next(g for g in j['rows'] if g['case_id']==c['id']);labels=['v4','v5'];order=labels[i%2:]+labels[:i%2];mapping=dict(zip('ab',order))
        payload={'case':c,'fixture_truth':fixture_truth(c),'historical_trace_limit':'Old answers have no full tool transcript; fixture facts are deterministic available truth, not proof of a tool read.',**{side:answers[(c['id'],l)] for side,l in mapping.items()}}
        if g['status']!='completed' or g['mapping']!=mapping or g['answer_binding']!=digest(payload) or g['system_sha256']!=hashlib.sha256(system.encode()).hexdigest() or g['n_conditions']!=2:raise ValueError('Judge answer/rubric binding changed')
        raw=read(folder/'main/raw-judges'/(c['id']+'.json'))
        if raw.get('finish_reasons') not in (['FinishReason.STOP'],['STOP']):raise ValueError('Judge response not normally completed')
        if g['raw_sha256']!=digest(raw) or parse_grades(raw['text'],2)!=g['grades'] or raw['usage']!=g['usage']:raise ValueError('Raw grade differs from parsed scores')
        price_usage('gemini-3.1-pro-preview',[g['usage']])
    verify_batch_provenance(folder,cs,r,j)
    # Recompute without trusting mutable stored summary selection.
    with runner.bound():result=runner.summarize_stage(folder,False)
    if not result['candidate_passed']:raise ValueError('Candidate failed frozen v5 development gate')
    hashes={n:sha(folder/n) for n in ['protocol.json','candidate.json','frozen.json','main/answers.json','main/judges.json']}
    trace_hashes={f.relative_to(folder).as_posix().replace('\\','/'):sha(f) for pattern in ['main/model-inputs/*.json','main/raw-judges/*.json'] for f in folder.glob(pattern)}
    for f in folder.glob('main/batch-*.json'):trace_hashes[f.relative_to(folder).as_posix()]=sha(f)
    for f in folder.glob('main/batch-requests/*.json'):trace_hashes[f.relative_to(folder).as_posix()]=sha(f)
    if (folder/'bounded-timeouts.json').exists():hashes['bounded-timeouts.json']=sha(folder/'bounded-timeouts.json')
    return {'schema_version':1,'suite':SUITE,'candidate_sha256':digest(candidate),'baseline_identity':identity(candidate['baseline']),'candidate_identity':identity(candidate['snapshot']),'condition':'v5','source_hashes':hashes,'trace_hashes':trace_hashes,'analysis':result,'coverage':coverage,'approved':True,'scope':'Separate development100pairs:1 known replay+99 new synthetic cases, no independent/user claims; exact two-template v5 and unchanged6 inherit approved v4.'}


def verify_batch_provenance(folder,cases,report,judges):
    import json
    from google import genai
    from scripts.eval.batch_agentic_judges import requests_digest
    from scripts.eval.clarification_v3 import fixture_truth,format_system,grade_schema
    from scripts.eval.v5_evidence_contract import check_batch
    folder=Path(folder);by={c['id']:c for c in cases};answers={(a['case_id'],a['condition']):a['answer'] for a in report['rows']};grades={g['case_id']:g for g in judges['rows']};seen=[]
    client=genai.Client(api_key='offline-serialization-only',vertexai=False)
    try:
        for path in folder.glob('main/batch-*.json'):
            job=read(path);entries=[];requests=[]
            for entry in job['entries']:
                cid=entry['case_id'];g=grades[cid];c=by[cid];entries.append({k:g[k] for k in ['key','case_id','mapping','answer_binding','system_sha256','n_conditions']});seen.append(cid)
                payload={'case':c,'fixture_truth':fixture_truth(c),'historical_trace_limit':'Old answers have no full tool transcript; fixture facts are deterministic available truth, not proof of a tool read.',**{side:answers[(cid,label)] for side,label in g['mapping'].items()}}
                requests.append({'contents':[{'role':'user','parts':[{'text':json.dumps(payload,ensure_ascii=False)}]}],'metadata':{'key':cid},'config':{'system_instruction':format_system(2),'temperature':0,'thinking_config':{'thinking_level':'low'},'max_output_tokens':2048,'response_mime_type':'application/json','response_json_schema':grade_schema(2)}})
            expected=json.loads(requests_digest(client,'gemini-3.1-pro-preview',requests));wire=read(folder/'main/batch-requests'/path.name);check_batch(job,wire,expected,entries)
    finally:client.close()
    if len(seen)!=100 or len(set(seen))!=100 or set(seen)!=set(by):raise ValueError('Batch grade coverage differs from frozen100')
