"""Followup candidate experiment: immutable historical baseline, bounded new calls."""
import asyncio,copy,hashlib,json,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
from scripts.eval import eval_budget
from scripts.prompt_release_workflow import read,identity,CONDITIONS
from app.core.prompt_release_control import _snapshot

def seed_baseline(original,candidate,folder):
    folder=Path(folder); source=Path(original)
    old=read(source/'paired.json')
    if hashlib.sha256((source/'paired.json').read_bytes()).hexdigest()!='116fd62dba5da079a0ee4596f1d4366c73619f63c2b4fc9f905bacd97041471e':raise ValueError('Historical baseline changed')
    if identity(old['prompt_snapshots']['v1'])!=identity(candidate['baseline']):raise ValueError('Baseline identity mismatch')
    result=copy.deepcopy(old);result['rows']=[r for r in old['rows'] if r['condition']=='v1']
    # Keep the historically executed manifest, including its original validation metadata.
    result['prompt_snapshots']={'v1':old['prompt_snapshots']['v1'],'v2':candidate['snapshot']}
    result['baseline_reuse']={'source_sha256':hashlib.sha256((source/'paired.json').read_bytes()).hexdigest(),'timing':'historical baseline; not contemporaneous randomized latency evidence'}
    result['hypothesis']='Reduce unnecessary requests for more input; retain correctness/freshness/no-write. Baseline floor=0 question markers; no improvement may be measurable.'
    folder.mkdir(parents=True,exist_ok=True)
    for name,value in [('paired.json',result),('frozen.json',read(source/'frozen.json'))]:
        with (folder/name).open('x',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return result

def campaign_guard(protocol):
    original=eval_budget.install_transport_guard
    def install(budget,stage):
        eval_budget.TOTAL=min(eval_budget.TOTAL,protocol['total_limit_usd'])
        eval_budget.LIMITS={k:min(v,protocol['stage_caps'][k]) for k,v in eval_budget.LIMITS.items()}
        return original(budget,stage)
    return patch.object(eval_budget,'install_transport_guard',install)

async def main(args):
    protocol=read(args.protocol)
    if args.mode=='seed':seed_baseline(ROOT/'docs/prompt_control/comparison',read(args.candidate),args.folder);return
    if not args.allow_paid:raise ValueError('Paid calls require explicit flag')
    with campaign_guard(protocol):
        if args.mode=='generate':
            from scripts.eval.benchmark_prompt_control import main as generate
            await generate(args.folder,args.candidate)
        else:
            from scripts.eval.judge_prompt_control import main as judge
            await judge(args.folder)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['seed','generate','judge']);p.add_argument('--folder',required=True);p.add_argument('--candidate');p.add_argument('--protocol',required=True);p.add_argument('--allow-paid',action='store_true')
    asyncio.run(main(p.parse_args()))
