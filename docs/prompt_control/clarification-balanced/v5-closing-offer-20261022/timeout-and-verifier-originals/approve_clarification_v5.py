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
    coverage={l:{n:0 for n in ['team.base','team.compact_followup']} for l in ['v4','v5']}
    for a in r['rows']:
        snap=r['snapshots'][a['condition']];meta=_snapshot(snap).metadata();c=by[a['case_id']]
        if a['input_key']!=request_key(c,request_spec(snap)) or any(a['prompt_metadata'].get(k)!=meta[k] for k in ['prompt_commit_ids','prompt_hashes','prompt_bundle_sha256']):raise ValueError('Per-attempt binding changed')
        if a['status'] not in ({'completed','blocked'} if a['condition']=='v4' else {'completed'}) or a['no_write'] is not True or a['model']!=CONDITIONS['model'] or not a['answer']:raise ValueError('Incomplete/unsafe serving attempt')
        if any(type(a.get(k)) not in (int,float) or not math.isfinite(a[k]) or a[k]<0 for k in ['ms','cost_usd']) or abs(a['cost_usd']-price_usage(CONDITIONS['model'],a['usage']))>1e-9:raise ValueError('Invalid measured cost/duration')
        if a.get('reused_from'):
            if a!=reuse_regression(c,snap):raise ValueError('Reused regression differs from original')
            continue
        trace=read(folder/'main/model-inputs'/(a['case_id']+'-'+a['condition']+'.json'))
        if trace['input_key']!=a['input_key'] or trace['fixture_truth']!=fixture_truth(c):raise ValueError('Trace input/fixture mismatch')
        systems=[m['content'] for group in trace['model_inputs'] for m in group if m['type']=='system']
        # Static template is the leading instruction; runtime appends role/evidence.
        # Use the longest registered prefix so v1 cannot borrow extended v4 text.
        used=[]
        for system in systems:
            matches=[(len(s['texts'][n]),label,n) for label,s in r['snapshots'].items() for n in coverage[label] if system==s['texts'][n] or system.startswith(s['texts'][n]+'\n')]
            if matches:
                length=max(x[0] for x in matches)
                used.extend(n for size,label,n in matches if size==length and label==a['condition'])
        if not used:raise ValueError('Actual primary prompt application missing')
        for n in set(used):coverage[a['condition']][n]+=1
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
    # Recompute without trusting mutable stored summary selection.
    with runner.bound():result=runner.summarize_stage(folder,False)
    if not result['candidate_passed']:raise ValueError('Candidate failed frozen v5 development gate')
    hashes={n:sha(folder/n) for n in ['protocol.json','candidate.json','frozen.json','main/answers.json','main/judges.json']}
    trace_hashes={f.relative_to(folder).as_posix().replace('\\','/'):sha(f) for pattern in ['main/model-inputs/*.json','main/raw-judges/*.json'] for f in folder.glob(pattern)}
    return {'schema_version':1,'suite':SUITE,'candidate_sha256':digest(candidate),'baseline_identity':identity(candidate['baseline']),'candidate_identity':identity(candidate['snapshot']),'condition':'v5','source_hashes':hashes,'trace_hashes':trace_hashes,'analysis':result,'coverage':coverage,'approved':True,'scope':'Separate development100pairs:1 known replay+99 new synthetic cases, no independent/user claims; exact two-template v5 and unchanged6 inherit approved v4.'}
