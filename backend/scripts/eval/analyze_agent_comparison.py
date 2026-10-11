"""Posthoc AgentEvals coverage plus state/schema contracts; raw runs preserved."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'artifacts/agentevals-runtime'))
from agentevals.trajectory.match import create_trajectory_match_evaluator
from scripts.eval.agent_evaluation import aggregate, grade_decision, validate_gold
from scripts.eval.analyze_frozen_rerank import interval
from scripts.eval.run_agent_comparison import minimum_path_excess


def trajectory(names):
    return [{'role': 'assistant', 'content': '', 'tool_calls':
             [{'function': {'name': n, 'arguments': '{}'}} for n in names]}]


def validate_source_identity(directory, dataset):
    identity = json.loads((directory / 'identity.json').read_text(encoding='utf8'))
    actual_sha = hashlib.sha256(dataset.read_bytes()).hexdigest()
    if actual_sha != identity.get('dataset_sha'):
        raise ValueError('Analysis dataset SHA differs from frozen experiment identity')
    snapshot = directory / 'dataset-snapshot.json'
    if not snapshot.exists() or hashlib.sha256(snapshot.read_bytes()).hexdigest() != actual_sha:
        raise ValueError('Frozen dataset snapshot differs from analysis dataset SHA')
    variants = identity.get('variants')
    if not isinstance(variants, list) or not variants:
        raise ValueError('Experiment identity has no frozen variants manifest')
    return set(variants)


def validate_result_variant(variant, allowed_variants):
    if variant not in allowed_variants:
        raise ValueError(f'Result variant {variant!r} is outside frozen variants manifest')


def main(args):
    gold = json.loads(args.dataset.read_text(encoding='utf8'))
    validate_gold(gold, {'decision': 30, 'flow': 10, 'safety': 20})
    cases = {r['id']: r for r in gold}
    allowed_variants = validate_source_identity(args.directory, args.dataset)
    source_identity = json.loads((args.directory/'identity.json').read_text(encoding='utf8'))
    rows = []
    for path in args.directory.glob('*.json'):
        row = json.loads(path.read_text(encoding='utf8'))
        if 'variant' not in row or 'id' not in row:
            continue
        case = cases[row['id']]
        validate_result_variant(row['variant'], allowed_variants)
        if case['domain'] != source_identity['domain'] or case['split'] != source_identity['split']:
            raise ValueError('Result case is outside frozen experiment domain/split')
        if case['domain'] == 'decision' and row.get('decisions'):
            decision = row['decisions'][0]
            probabilities = decision['probabilities']
            raw_choice = max(probabilities, key=probabilities.get) if probabilities else None
            row['jev_raw_choice'] = raw_choice
            row['jev_raw_selection_ok'] = raw_choice in case['acceptable_next']
            row['jev_enforced'] = decision['choice'] is not None and not decision['fallback_reason']
        if row['status'] == 'completed':
            if case['domain'] == 'decision':
                names = [c['name'] for c in row['requested_calls']]
                row['grade_original'] = {k: row[k] for k in ('goal_ok', 'selection_ok', 'arguments_ok')}
                row.update(grade_decision(case, row['requested_calls']))
                row['goal_ok'] = row['goal_ok'] and row['runtime_status'] == 'completed'
                if names and len(row['executed_calls']) != len(names):
                    row.update(goal_ok=False, arguments_ok=False)
                reference = [n for n in case['acceptable_next'] if n != 'finish']
                evaluator = create_trajectory_match_evaluator(trajectory_match_mode='subset', tool_args_match_mode='ignore')
                score = evaluator(outputs=trajectory(names), reference_outputs=trajectory(reference))
                row['trajectory_match'] = bool(score['score']) and (bool(names) or 'finish' in case['acceptable_next'])
                row['goal_ok'] = row['goal_ok'] and row['trajectory_match']
            else:
                names = [e['tool'] for e in row['events'] if e['type'] == 'tool_succeeded']
                row['excess_tool_calls'] = minimum_path_excess(names, case['required_tools'])
                evaluator = create_trajectory_match_evaluator(trajectory_match_mode='superset', tool_args_match_mode='ignore')
                score = evaluator(outputs=trajectory(names), reference_outputs=trajectory(case['required_tools']))
                row['trajectory_match'] = bool(score['score'])
                row['goal_ok'] = row['goal_ok'] and row['trajectory_match']
        row['split'] = case['split']; row['domain'] = case['domain']; rows.append(row)
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['location'] or 'flow', row['variant'])].append(row)
    summary = {}
    for (loc, variant), group in grouped.items():
        values = aggregate(group)
        decisions = [r for r in group if 'jev_raw_selection_ok' in r]
        if decisions:
            values['jev_raw_selection_rate'] = sum(r['jev_raw_selection_ok'] for r in decisions)/len(decisions)
            values['jev_enforced_count'] = sum(r['jev_enforced'] for r in decisions)
            values['confidence_bins'] = {}
            for low, high in ((0, .5), (.5, .7), (.7, .9), (.9, 1.01)):
                selected = [r for r in decisions if r['decisions'][0]['confidence'] is not None and
                            low <= r['decisions'][0]['confidence'] < high]
                values['confidence_bins'][f'{low}-{high}'] = {'n': len(selected),
                    'selection_errors': sum(not r['jev_raw_selection_ok'] for r in selected)}
        summary[f'{loc}/{variant}'] = values
    # Never count three repeats as independent cases. Average within scenario.
    paired = {}
    for location in {r['location'] for r in rows}:
        subset = [r for r in rows if r['location'] == location]
        baselines = {(r['id'], r['repeat']): r for r in subset if r['variant'] == 'gemini'}
        for variant in {r['variant'] for r in subset} - {'gemini'}:
            differences = defaultdict(list)
            for row in subset:
                other = baselines.get((row['id'], row['repeat']))
                if row['variant'] == variant and other:
                    differences[row['group']].append(float(row.get('goal_ok', False)) - float(other.get('goal_ok', False)))
            paired[f'{location or "flow"}/{variant}'] = interval([sum(v)/len(v) for v in differences.values()]) if differences else None
    usage = Counter()
    for row in rows:
        for e in row.get('decisions', []):
            usage.update({'jev_'+k:v for k,v in e['usage'].items()})
        for output in row.get('provider_outputs', []):
            usage.update({'gemini_'+k:v for k,v in output['usage'].items() if isinstance(v,int)})
    report = {'scope': 'development/heldout synthetic contracts; repeated decisions not independent samples; no production adoption',
              'evaluator': 'agentevals 0.0.9 trajectory subset/superset ignoring args plus independent schema/state/policy contracts',
              'scored_dataset_sha': hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
              'source_identity': source_identity,
              'summary': summary, 'paired_goal_differences': paired, 'usage': dict(usage), 'rows': rows}
    (args.directory / 'analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'summary': summary, 'paired': paired},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, default=ROOT.parent/'docs/agent_experiments/gold_agent60_v2.json')
    main(parser.parse_args())
