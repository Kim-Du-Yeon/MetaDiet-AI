"""Explicit retrospective policy revision; original holdout files/gate stay immutable.

Strict raw-evidence verifier is intentionally isolated from the original suite.
It reuses original parsers/scorers, never old selection flags or generated scores.
"""
import copy,hashlib,math
from pathlib import Path
from scripts.eval.clarification_holdout import (ROOT,SOURCE,SUITE,CONDITIONS,COHORT_SHA,read,sha,supported,cohort_sha,assert_novel)
from app.core.prompt_release_control import digest
EVIDENCE=ROOT/'docs/prompt_control/clarification-balanced/v4-independent-20261022'
REVIEW=EVIDENCE.parent/'v4-approval-policy-v2-20261022'
REVIEW_SUITE='clarification-candidate-policy-review-v2'
POLICY_SHA='fd1e3c6885d7b58fb1d6945367eff05d2e73a95c4e0edee1dedd9b14ff440e5c'
SOURCE_TREE_SHA='e2c2a2b3806fe89c53e87c68c6aba79cdb299ba763a429683f89569eb4123932'


def select(values):
    a,b=values['v1'],values['v4']
    checks={
        'baseline100_attempted_and_accounted':a['expected']==a['attempted']==100 and a['usage_complete'],
        'candidate100_normal_and_accounted':b['expected']==b['attempted']==b['judged']==100 and b['generation_failures']==0 and b['usage_complete'],
        'correct':b['correct']>=98 and b['correct']>=a['correct']-1,
        'faithful':b['faithful']>=98 and b['faithful']>=a['faithful']-1,
        'behavior':b['passed']>=max(98,a['passed']),
        'required':b['required_recall_numerator']>=49,
        'unsafe':b['unsafe_commitments']==0,
        'fresh':b['fresh']==100,
        'no_write':b['no_write']==100,
        'unnecessary':b['unnecessary_all']<=min(2,a['unnecessary_all']),
        'p95':b['p95_ms']<=a['p95_ms']*1.25,
        'cost':b['cost_usd']<=a['cost_usd']*1.25,
    }
    return {'candidate_approved':all(checks.values()),'checks':checks,'baseline_failures_retained':a['generation_failures'],'policy_kind':'retrospective_revision_not_new_preregistered_trial','actual_user_ab':False}


def code_hashes():
    files=['backend/scripts/eval/clarification_approval_review.py','backend/scripts/prompt_release_workflow.py']
    return {n:hashlib.sha256((ROOT/n).read_text(encoding='utf-8-sig').encode()).hexdigest() for n in files}


def validate_review(folder):
    folder=Path(folder)
    if digest(read(folder/'policy.json'))!=POLICY_SHA:raise ValueError('Approval policy changed')
    hashes=read(folder/'source-hashes.json')
    if digest(hashes)!=SOURCE_TREE_SHA:raise ValueError('Original source inventory changed')
    actual={p.relative_to(EVIDENCE).as_posix():sha(p) for p in sorted(EVIDENCE.rglob('*')) if p.is_file()}
    if actual!=hashes:raise ValueError('Original evidence changed')
    p=read(EVIDENCE/'protocol.json')
    if cohort_sha(read(EVIDENCE/'frozen.json'))!=COHORT_SHA:raise ValueError('Frozen cases changed')
    assert_novel(read(EVIDENCE/'frozen.json'))
    # Changed approval dispatcher is outside serving/generation. Every evaluator helper stays frozen.
    for n,h in p['code_sha256'].items():
        if n=='backend/scripts/prompt_release_workflow.py':continue
        if hashlib.sha256((ROOT/n).read_text(encoding='utf-8-sig').encode()).hexdigest()!=h:raise ValueError('Original evaluator helper changed')
    for n,h in p['historical_sha256'].items():
        if sha(SOURCE/n)!=h:raise ValueError('Historical diagnostic evidence changed')
    return p


def summarize(cases,report,judges):
    from scripts.eval.clarification_cases import summarize as case_summary
    result={}
    for label in ['v1','v4']:
        answers=[copy.deepcopy(a) for a in report['rows'] if a['condition']==label];grades=[]
        for row in judges['rows']:
            side=next(s for s,v in row['mapping'].items() if v==label)
            grades.append({'case_id':row['case_id'],'status':row['status'],**row['grades'][side]})
        by={g['case_id']:g for g in grades}
        for a in answers:a['fresh']=by[a['case_id']]['fresh_current_values'] is True
        completed={a['case_id'] for a in answers if a['status']=='completed'}
        counted=[g for g in grades if g['case_id'] in completed and g['status']=='completed']
        times=sorted(a['ms'] for a in answers);v=case_summary(cases,answers,grades)
        v.update(correct=sum(g['correct'] for g in counted),faithful=sum(g['faithful'] for g in counted),unnecessary_all=sum(g['unnecessary_request'] is True for g in grades),generation_failures=len(answers)-len(completed),p95_ms=times[max(0,math.ceil(len(times)*.95)-1)],mean_ms=sum(times)/len(times),cost_usd=sum(a['cost_usd'] for a in answers),usage_complete=all(a.get('usage') and a.get('cost_usd') is not None for a in answers))
        result[label]=v
    return result


def verify(candidate,folder,key):
    """Recompute the gate and bindings, never sign an asserted summary flag."""
    from scripts.prompt_release_workflow import validate_candidate,identity
    from scripts.eval.clarification_execution import request_spec,price_usage
    from scripts.eval.clarification_cases import request_key
    from scripts.eval.clarification_v3 import fixture_truth,format_system,parse_grades
    from app.core.prompt_release_control import _snapshot
    from scripts.eval.run_clarification_comparison import versions
    if versions()!=CONDITIONS['packages']:raise ValueError('Evaluation package environment changed')
    validate_candidate(candidate,key);supported(candidate);review_folder=Path(folder);p=validate_review(review_folder);folder=EVIDENCE
    if read(folder/'candidate.json')!=candidate:raise ValueError('Approval candidate differs from evaluated exact commits')
    if identity(candidate['baseline'])!=identity(read(SOURCE/'source-answers.json')['snapshots']['v1']):raise ValueError('Historical baseline changed')
    if not read(SOURCE/'main/summary.json')['new_protocol_passed']:raise ValueError('Historical diagnostic gate failed')
    r=read(folder/'main/answers.json');j=read(folder/'main/judges.json');cs=read(folder/'frozen.json');by={c['id']:c for c in cs}
    if r['experiment']!=SUITE or r['conditions']!=CONDITIONS or r['cases_sha256']!=cohort_sha(cs) or r['protocol_sha256']!=digest(p) or r['runner_sha256']!=digest(p['code_sha256']):raise ValueError('Execution identity changed')
    if identity(r['snapshots']['v1'])!=identity(candidate['baseline']) or identity(r['snapshots']['v4'])!=identity(candidate['snapshot']):raise ValueError('Evaluated snapshot mismatch')
    expected={(c['id'],l) for c in cs for l in ['v1','v4']};keys=[(a['case_id'],a['condition']) for a in r['rows']]
    if len(keys)!=200 or set(keys)!=expected:raise ValueError('Require200 unique attempts')
    coverage={l:{n:0 for n in ['team.base','team.compact_followup']} for l in ['v1','v4']}
    for a in r['rows']:
        snap=r['snapshots'][a['condition']];meta=_snapshot(snap).metadata();c=by[a['case_id']]
        if a['input_key']!=request_key(c,request_spec(snap)) or any(a['prompt_metadata'].get(k)!=meta[k] for k in ['prompt_commit_ids','prompt_hashes','prompt_bundle_sha256']):raise ValueError('Per-attempt binding changed')
        if a['status'] not in ({'completed','blocked'} if a['condition']=='v1' else {'completed'}) or a['no_write'] is not True or a['model']!=CONDITIONS['model'] or not a['answer']:raise ValueError('Incomplete/unsafe serving attempt')
        if any(type(a.get(k)) not in (int,float) or not math.isfinite(a[k]) or a[k]<0 for k in ['ms','cost_usd']) or abs(a['cost_usd']-price_usage(CONDITIONS['model'],a['usage']))>1e-9:raise ValueError('Invalid measured cost/duration')
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
        g=next(g for g in j['rows'] if g['case_id']==c['id']);labels=['v1','v4'];order=labels[i%2:]+labels[:i%2];mapping=dict(zip('ab',order))
        payload={'case':c,'fixture_truth':fixture_truth(c),'historical_trace_limit':'Old answers have no full tool transcript; fixture facts are deterministic available truth, not proof of a tool read.',**{side:answers[(c['id'],l)] for side,l in mapping.items()}}
        if g['status']!='completed' or g['mapping']!=mapping or g['answer_binding']!=digest(payload) or g['system_sha256']!=hashlib.sha256(system.encode()).hexdigest() or g['n_conditions']!=2:raise ValueError('Judge answer/rubric binding changed')
        raw=read(folder/'main/raw-judges'/(c['id']+'.json'))
        if raw.get('finish_reasons') not in (['FinishReason.STOP'],['STOP']):raise ValueError('Judge response not normally completed')
        if g['raw_sha256']!=digest(raw) or parse_grades(raw['text'],2)!=g['grades'] or raw['usage']!=g['usage']:raise ValueError('Raw grade differs from parsed scores')
        price_usage('gemini-3.1-pro-preview',[g['usage']])
    # Recompute without trusting mutable stored summary selection.
    values=summarize(cs,r,j);result=select(values)
    if not result['candidate_approved']:raise ValueError('Candidate failed separate safety/quality policy')
    hashes={n:sha(folder/n) for n in ['protocol.json','candidate.json','frozen.json','main/answers.json','main/judges.json']}
    trace_hashes={f.relative_to(folder).as_posix().replace('\\','/'):sha(f) for pattern in ['main/model-inputs/*.json','main/raw-judges/*.json'] for f in folder.glob(pattern)}
    return {'schema_version':1,'suite':REVIEW_SUITE,'review_policy_sha256':POLICY_SHA,'review_code_sha256':code_hashes(),'original_source_tree_sha256':SOURCE_TREE_SHA,'candidate_sha256':digest(candidate),'baseline_identity':identity(candidate['baseline']),'candidate_identity':identity(candidate['snapshot']),'condition':'v4','source_hashes':hashes,'trace_hashes':trace_hashes,'analysis':{'decision':result,'conditions':values},'coverage':coverage,'approved':True,'scope':'Retrospective approval-policy revision using unchanged synthetic100 paired evidence; original gate remains failed. Not new independent validation or live-user outcomes.'}
