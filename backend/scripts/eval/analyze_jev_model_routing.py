"""Validate100 pairs and replay saved Jev decisions without API calls."""
import argparse
import asyncio
from collections import Counter
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.core.jev import Decision
from app.agents.runtime import ExecutionBudget
from scripts.eval.jev_model_router import RoutingRequest,select_model


async def analyze(folder):
    raw=(folder/'paired.json').read_bytes()
    report=json.loads(raw)
    frozen=(folder/'frozen.json').read_bytes()
    if hashlib.sha256(frozen).hexdigest()!=report['cases_sha256']:
        raise ValueError('Frozen cases hash mismatch')
    cases=json.loads(frozen)
    expected={(c['id'],mode) for c in cases for mode in ['rules','jev']}
    found=[(r['case_id'],r['condition']) for r in report['rows']]
    if len(cases)!=100 or len(found)!=200 or len(set(found))!=200 or set(found)!=expected:
        raise ValueError('Missing/duplicate100 matched pairs')
    settings=SimpleNamespace(**report['model_config'])
    case_map={c['id']:c for c in cases}
    matches=[]
    for row in report['rows']:
        if row['condition']!='jev': continue
        event=row.get('decision')
        if not event: raise ValueError('Missing actual decision')
        data={field.name:event[field.name] for field in fields(Decision) if field.name in event}
        data['candidates']=tuple(data['candidates'])
        client=SimpleNamespace(choose=AsyncMock(return_value=Decision(**data)))
        case=case_map[row['case_id']]
        replay=await select_model(RoutingRequest(task=case['task'],text=case['text']),mode='jev',
            settings=settings,client=client,budget=ExecutionBudget())
        matches.append(all(row[k]==replay[k] for k in ['status','band','model','source','jev_attempted']))
    if len(matches)!=100 or not all(matches):
        raise ValueError('Saved decisions differ after defensive validation')
    rows=[r for r in report['rows'] if r['condition']=='jev']
    models=dict(Counter(r['decision']['model'] for r in rows))
    complete_usage=all('input_tokens' in r['decision']['usage'] and 'output_tokens' in r['decision']['usage'] for r in rows)
    inputs=sum(r['decision']['usage'].get('input_tokens',0) for r in rows)
    known_model=set(models).issubset({'jev-1.13.0','jev-1.14.0'})
    return {'scope':'matched_router_only_and_saved_decision_replay_not_new_live_measurement',
        'report_sha256_utf8_lf':hashlib.sha256(raw.decode().replace('\r\n','\n').encode()).hexdigest(),
        'attempts_per_condition':100,'exact_pairs':True,'replay_matching':sum(matches),
        'returned_models':models,'all_usage_available':complete_usage,
        'router_jev_cost_estimate_usd':inputs*.042/1e6 if complete_usage and known_model else None,
        'pricing':{'checked':'2026-10-19','usd_per_million_input':.042,'output':'free',
            'source':'https://docs.typesafe.ai/models'},
        'scope_exclusions':['Downstream Gemini generation','Ragas','latest actual intake reflection',
            'Real-user or clinical accuracy','Provider invoice or infrastructure cost']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    output=args.directory/'validation.json'
    if output.exists(): raise SystemExit('Refusing to overwrite evidence')
    result=asyncio.run(analyze(args.directory))
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': main()
