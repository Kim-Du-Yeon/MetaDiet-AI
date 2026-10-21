"""One outstanding Batch job; resume from frozen saved answers, never regenerate."""
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import batch_agentic_judges as batches
from eval_budget import BudgetStop, micros


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


@contextmanager
def campaign_lock(path):
    lock = path.with_suffix(path.suffix + '.lock')
    try:
        file = lock.open('x')
    except FileExistsError:
        raise ValueError('Campaign is locked; inspect interrupted run before retry')
    try:
        file.close()
        yield
    finally:
        lock.unlink()


def advance(client, path, model, entries, requests, budget, *, max_entries=10, submit_next=True):
    """Collect at most one job, settle verified usage, submit at most one chunk.

    No sleeps/polling loop. Re-running is explicit, preserves the same ledger,
    and cannot duplicate an ambiguous submission. No model generation occurs.
    """
    if type(max_entries) is not int or not 1 <= max_entries <= 100:
        raise ValueError('Chunk size must be 1..100')
    if len(entries) != len(requests) or len({e['key'] for e in entries}) != len(entries):
        raise ValueError('Unique entries and matching requests required')
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    identity = {
        'model': model, 'ledger': budget.path, 'max_entries': max_entries,
        'entries_sha256': hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'requests_sha256': hashlib.sha256(batches.requests_digest(client, model, requests).encode()).hexdigest(),
    }
    with campaign_lock(path):
        if path.exists():
            saved = json.loads(path.read_text(encoding='utf-8'))
            if saved.get('identity') != identity:
                raise ValueError('Frozen campaign input/model/ledger/config changed')
        else:
            saved = {'type': 'split_batch_campaign', 'identity': identity, 'entries': entries, 'jobs': [], 'state': 'ready'}
            with path.open('x', encoding='utf-8') as file:
                file.write(json.dumps(saved, ensure_ascii=False, indent=2))
        if saved['state'] == 'completed':
            return 'completed'
        jobs = saved['jobs']
        if jobs and jobs[-1]['state'] != 'settled':
            current = jobs[-1]
            job_path = path.parent / current['path']
            if not job_path.exists():
                raise ValueError('Interrupted chunk claim; inspect before any resubmission')
            collected = batches.collect(client, job_path, budget=budget)
            if not collected['terminal']:
                return 'pending'
            if not collected['budget_settled']:
                saved['state'] = 'usage_unverified'
                save(path, saved)
                return 'usage_unverified'
            current['state'] = 'settled'
            save(path, saved)
        start = jobs[-1]['end'] if jobs else 0
        if start == len(entries):
            records=[];keys=set()
            for job in jobs:
                grades=(path.parent/job['path']).with_suffix('.grades.jsonl')
                for line in grades.read_text(encoding='utf-8').splitlines():
                    row=json.loads(line)
                    key=(row['attempt_id'],row['condition'])
                    if key in keys:raise ValueError('Duplicate campaign grade')
                    keys.add(key);records.append(row)
            output=path.with_suffix('.grades.jsonl')
            text=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in records)
            if output.exists() and output.read_text(encoding='utf-8')!=text:
                raise ValueError('Existing combined grades differ; preserve and inspect')
            if not output.exists():
                temporary=output.with_suffix('.jsonl.tmp')
                temporary.write_text(text,encoding='utf-8');temporary.replace(output)
            saved['state'] = 'completed'
            save(path, saved)
            return 'completed'
        if not submit_next:
            saved['state']='ready'
            save(path,saved)
            return 'ready'
        available = micros(budget.available('judge'))
        end = start
        for stop in range(start + 1, min(len(entries), start + max_entries) + 1):
            cost = batches.batch_cost(client, model, requests[start:stop])
            if micros(cost) > available:
                break
            end = stop
        if end == start:
            # This atomically persists the stop reason. No request is submitted.
            budget.reserve('judge', batches.batch_cost(client, model, requests[start:start+1]), check_only=True)
            raise BudgetStop('No affordable Batch entry')
        directory = path.with_suffix('.parts')
        directory.mkdir(exist_ok=True)
        job_path = directory / f'job-{len(jobs):04d}.json'
        jobs.append({'start': start, 'end': end, 'path': str(job_path.relative_to(path.parent)), 'state': 'submission_entered'})
        saved['state'] = 'pending'
        save(path, saved)  # Claim first; unknown submission must never be replayed.
        batches.submit_once(client, job_path, model, requests[start:end], entries[start:end], budget=budget)
        jobs[-1]['state'] = 'submitted'
        save(path, saved)
        return 'pending'
