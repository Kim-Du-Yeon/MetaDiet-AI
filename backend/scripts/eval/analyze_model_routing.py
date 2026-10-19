"""Verify frozen identities and exact case pairs before aggregating live shards."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.eval.model_routing_support import summarize, deployment_gate, summarize_judge_cost, require_prompt_v1


def text_sha256(raw):
    """Canonical UTF-8/LF identity survives Windows writes and Git checkout."""
    return hashlib.sha256(raw.decode('utf-8').replace('\r\n','\n').encode('utf-8')).hexdigest()


def verify_frozen_hash(raw,expected):
    if text_sha256(raw)!=expected:
        raise ValueError('Frozen dataset hash mismatch')


def combine(reports,cases):
    if not reports:
        raise ValueError('Missing shards')
    first = reports[0]
    count = first['shards']
    if len(reports)!=count or {r['shard'] for r in reports}!=set(range(count)):
        raise ValueError('Missing or duplicate shard')
    identity = ('protocol','cases_sha256','model_config','shards')
    if first['protocol']!='task-balanced-pair-order-v2' or any(
        any(r[k]!=first[k] for k in identity) for r in reports):
        raise ValueError('Mixed experiment identity')
    if any(r.get('prompt_metadata') != first.get('prompt_metadata') for r in reports):
        raise ValueError('Mixed prompt identity')
    require_prompt_v1(first.get('prompt_metadata') or {})
    indices = {c['id']:i for i,c in enumerate(cases)}
    tasks = {c['id']:c['task'] for c in cases}
    if len(indices)!=100 or len(cases)!=100:
        raise ValueError('Expected exactly100 frozen cases')
    seen,rows = set(),[]
    for report in reports:
        for row in report['rows']:
            pair = (row['case_id'],row['condition'])
            if pair in seen: raise ValueError('duplicate case pair')
            if (row['case_id'] not in indices or row['condition'] not in {'baseline','routing'} or
                row['task']!=tasks[row['case_id']] or indices[row['case_id']]%count!=report['shard']):
                raise ValueError('Foreign case/task/shard')
            seen.add(pair)
            # The original v2 logger used substring402 and could match retry
            # seconds81402. Preserve raw error and normalize only unambiguous type.
            row = dict(row)
            if 'ratelimit' in (row.get('error') or {}).get('type','').lower():
                row['normalized_error'] = 'quota_exhausted'
            rows.append(row)
    if seen!={(c['id'],mode) for c in cases for mode in ('baseline','routing')}:
        raise ValueError('Missing case pair')
    groups = {mode:[r for r in rows if r['condition']==mode] for mode in ('baseline','routing')}
    summary = {mode:summarize(items) for mode,items in groups.items()}
    by_task = {task:{mode:summarize([r for r in items if r['task']==task])
        for mode,items in groups.items()} for task in sorted(set(tasks.values()))}
    judges = [row for report in reports for row in report.get('judge_rows', [])]
    expected_judges = {(c['id'], mode) for c in cases if c['task']=='agent' for mode in ('baseline', 'routing')}
    judge_pairs = [(row['case_id'], row['condition']) for row in judges]
    judge_complete = (all(r['judge_status']=='completed' for r in reports) and
        len(judge_pairs)==len(expected_judges) and set(judge_pairs)==expected_judges and
        all(row['status']=='completed' for row in judges))
    judge_cost = summarize_judge_cost(judges)
    judge_cost_complete = all(group['cost_complete'] for group in judge_cost.values())
    return {'scope':'same_frozen100_cases_per_condition_three_independent_workers',
        'protocol':first['protocol'],'cases_sha256':first['cases_sha256'],
        'model_config':first['model_config'],'prompt_metadata':first.get('prompt_metadata'),
        'summary':summary,'by_task':by_task,
        'judge_rows': judges, 'judge_cost': judge_cost,
        'judge_cost_complete': judge_cost_complete,
        'generation_plus_judge_cost_usd': {mode:
            summary[mode]['known_cost_usd'] + judge_cost[mode]['known_cost_usd']
            if summary[mode]['cost_complete'] and judge_cost[mode]['cost_complete'] else None
            for mode in ('baseline', 'routing')},
        'error_reasons':{mode:dict(Counter(r.get('normalized_error') or (r.get('error') or {}).get('reason',r['status'])
            for r in items if r['status']!='completed')) for mode,items in groups.items()},
        'judge_complete':judge_complete,
        'deployment_gate':judge_cost_complete and deployment_gate(summary['baseline'],summary['routing'],
            judge_complete=judge_complete,by_task=by_task),
        'rows':sorted(rows,key=lambda r:(r['case_id'],r['condition'])),
        'limitations':['Synthetic development tasks, not real-user or clinical quality.',
            'Failures and deterministic zero-model routes remain in denominators.',
            '429 rejection times are not successful-generation speed evidence.',
            'No deployment if Pro judge or complete cost evidence is unavailable.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folders',nargs='+',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists(): raise SystemExit('Refusing to overwrite evidence')
    reports,provenance = [],[]
    for folder in args.folders:
        raw = (folder/'paired.json').read_bytes()
        report = json.loads(raw)
        frozen = (folder/'frozen.json').read_bytes()
        verify_frozen_hash(frozen,report['cases_sha256'])
        reports.append(report)
        provenance.append({'folder':folder.name,'report_sha256':text_sha256(raw)})
    result = combine(reports,json.loads(frozen))
    result['inputs'] = provenance
    result['text_hash_method'] = 'sha256-UTF8-LF'
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:result[k] for k in ('summary','error_reasons','judge_complete','deployment_gate')},ensure_ascii=False))


if __name__=='__main__': main()
