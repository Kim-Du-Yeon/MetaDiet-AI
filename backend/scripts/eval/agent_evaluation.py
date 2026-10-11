"""Gold contracts and honest denominators for synthetic Agent experiments."""
from collections import Counter
import re
import numpy as np


def asks_for_quantity(text):
    for sentence in re.split(r'[\n。.!]', text):
        quantity = re.search(r'양|그램|얼마|몇\s*(?:g|그람)|\b(?:grams?|g)\b', sentence, re.I)
        request = re.search(r'\?|알려\s*(?:주세요|주실|줘)|말씀해\s*주세요|몇.*(?:나요|습니까)', sentence)
        if quantity and request:
            return True
    return False


def validate_gold(rows, expected_counts=None):
    ids, groups = set(), {}
    for row in rows:
        if row['id'] in ids:
            raise ValueError('Duplicate case id')
        ids.add(row['id'])
        if not row.get('review', {}).get('reviewer') or not row['review'].get('scope'):
            raise ValueError('Missing scenario review provenance')
        if row['split'] not in {'dev', 'heldout'}:
            raise ValueError('Invalid split')
        if groups.setdefault(row['group'], row['split']) != row['split']:
            raise ValueError('Scenario group leaks across splits')
        if row['domain'] == 'decision':
            if not set(row['acceptable_next']) <= set(row['allowed_tools']) | {'finish'}:
                raise ValueError('Gold action exceeds offered permissions')
        elif row['domain'] not in {'flow', 'safety'}:
            raise ValueError('Unknown evaluation domain')
    if expected_counts and Counter(r['domain'] for r in rows) != Counter(expected_counts):
        raise ValueError('Gold domain counts do not match the plan')


def grade_decision(case, calls):
    names = [c['name'] for c in calls] or ['finish']
    violations = sum(n not in case['allowed_tools'] for n in names if n != 'finish')
    route_ok = bool(names) and all(n in case['acceptable_next'] for n in names)
    arguments_ok = all(all(c['args'].get(k) == v for k, v in case['constraints'].get(c['name'], {}).items())
                       for c in calls)
    return {'selection_ok': route_ok, 'arguments_ok': arguments_ok,
            'policy_violations': violations, 'goal_ok': route_ok and arguments_ok and not violations}


def aggregate(rows):
    n = len(rows)
    completed = [r for r in rows if r['status'] == 'completed']
    return {'n': n, 'completed': len(completed), 'failed': n - len(completed),
            'goal_rate': sum(r.get('goal_ok', False) and r['status'] == 'completed' for r in rows) / n if n else None,
            'p50_seconds': float(np.percentile([r['seconds'] for r in rows], 50)) if n else None,
            'p95_seconds': float(np.percentile([r['seconds'] for r in rows], 95)) if n else None,
            'model_calls': sum(r.get('model_calls', 0) for r in rows),
            'tool_calls': sum(r.get('tool_calls', 0) for r in rows),
            'excess_tool_calls': sum(r.get('excess_tool_calls', 0) for r in rows),
            'fallbacks': sum(r.get('fallbacks', 0) for r in rows),
            'policy_violations': sum(r.get('policy_violations', 0) for r in rows)}
