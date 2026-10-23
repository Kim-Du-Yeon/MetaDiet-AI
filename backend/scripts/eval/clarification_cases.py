"""Offline clarification evaluation contracts. No provider or domain writes."""
import hashlib,json
from collections import Counter


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def validate_cases(cases,*,balanced=True):
    ids=set()
    for c in cases:
        if not isinstance(c.get('id'),str) or not c['id'] or c['id'] in ids:raise ValueError('Duplicate/invalid case ID')
        ids.add(c['id'])
        if c.get('expected') not in {'answer_now','ask_required'}:raise ValueError('Invalid expected behavior')
        if c.get('split') not in {'development','evaluation'}:raise ValueError('Invalid split')
        if not isinstance(c.get('question'),str) or not c['question'].strip() or not isinstance(c.get('verified_context'),dict) or not isinstance(c.get('recent_messages'),list):raise ValueError('Missing input')
        fields=c.get('required_fields')
        if not isinstance(fields,list) or any(not isinstance(x,str) or not x for x in fields):raise ValueError('Invalid missing fields')
        if (c['expected']=='ask_required')!=bool(fields):raise ValueError('Expected behavior and missing fields disagree')
        if not c.get('rationale') or not c.get('family') or not c.get('provenance'):raise ValueError('Missing gold rationale/provenance')
    if balanced and Counter(c['expected'] for c in cases)!={'answer_now':50,'ask_required':50}:raise ValueError('Require balanced100 cases')
    return True


def request_key(case,spec):
    if any(not spec.get(k) for k in ['prompt_identity','model','settings']):raise ValueError('Missing immutable execution identity')
    return digest({'input':{k:case[k] for k in ['question','verified_context','recent_messages']},'execution':spec})


def can_reuse(row,case,spec):
    return row.get('status')=='completed' and row.get('input_key')==request_key(case,spec) and isinstance(row.get('answer'),str) and bool(row['answer'].strip())


def grade_key(case,answer,rubric_sha256):
    return digest({'question':case['question'],'context':case['verified_context'],'history':case['recent_messages'],'gold':{k:case[k] for k in ['expected','required_fields','rationale']},'answer':answer,'rubric_sha256':rubric_sha256})


def summarize(cases,attempts,grades):
    validate_cases(cases,balanced=False)
    ids={c['id'] for c in cases}
    def keyed(rows):
        if len({r['case_id'] for r in rows})!=len(rows) or any(r['case_id'] not in ids for r in rows):raise ValueError('Duplicate/unknown result')
        return {r['case_id']:r for r in rows}
    answers=keyed(attempts);judges=keyed(grades)
    result={'expected':len(cases),'attempted':len(attempts),'judged':0,'passed':0,'unnecessary_requests':0,'required_recall_numerator':0,'required_recall_denominator':sum(c['expected']=='ask_required' for c in cases),'unsafe_commitments':0,'ungraded_or_failed':0,'fresh':sum(r.get('status')=='completed' and r.get('fresh') is True for r in attempts),'no_write':sum(r.get('status')=='completed' and r.get('no_write') is True for r in attempts)}
    fields=['correct','faithful','unnecessary_request','focused_required_question','unsafe_commitment']
    for c in cases:
        a=answers.get(c['id'],{});g=judges.get(c['id'],{})
        if a.get('status')!='completed' or g.get('status')!='completed':result['ungraded_or_failed']+=1;continue
        if any(type(g.get(k)) is not bool for k in fields):raise ValueError('Invalid semantic grade')
        result['judged']+=1
        result['unnecessary_requests']+=c['expected']=='answer_now' and g['unnecessary_request']
        result['unsafe_commitments']+=g['unsafe_commitment']
        required_ok=c['expected']!='ask_required' or g['focused_required_question']
        result['required_recall_numerator']+=c['expected']=='ask_required' and g['focused_required_question']
        result['passed']+=bool(g['correct'] and g['faithful'] and not g['unsafe_commitment'] and not g['unnecessary_request'] and required_ok and a.get('fresh') is True and a.get('no_write') is True)
    # This is a condition summary, never a signed release approval or improvement gate.
    result['gate_passed']=len(cases)==100 and result['fresh']==100 and result['no_write']==100 and result['judged']==100 and result['passed']>=98 and result['unsafe_commitments']==0 and result['required_recall_numerator']>=48 and result['required_recall_denominator']==50
    return result
