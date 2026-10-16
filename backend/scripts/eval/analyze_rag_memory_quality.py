"""Strict paired retrieval analysis; missing answers are not fabricated scores."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.eval.rag_validation_support import summarize_rows,validate_frozen,memory_gate


def rates(rows):
    n=len(rows)
    return {key:sum(r.get('status')=='completed' and bool(r.get(key)) for r in rows)/n if n else None
            for key in ('source_hit','page_hit','delivered_page_hit','excerpt_hit','grounded')}


def compare(folder):
    if not (folder/'frozen.json').is_file():
        raise ValueError('Frozen input missing')
    frozen=json.loads((folder/'frozen.json').read_text(encoding='utf8'));validate_frozen(frozen)
    expected=Counter((c['id'],repeat) for c in frozen['cases'] for repeat in range(3))
    results={};all_rows={}
    for mode in ('dense_fallback','hybrid'):
        rows=[];memories=[]
        for repeat in range(3):
            path=folder/f'{mode}-r{repeat}.json'
            if not path.is_file():
                raise ValueError('Missing repeat; do not reduce denominator')
            report=json.loads(path.read_text(encoding='utf8'))
            if report['identity']!=frozen['identity'] or report['mode']!=mode:
                raise ValueError('Condition identity mismatch')
            rows.extend(report['rows']);memories.append(report['memory'])
        if len(rows)!=120 or Counter((r['id'],r['repeat']) for r in rows)!=expected:
            raise ValueError('Incomplete/duplicate paired attempts')
        if any(r['status']=='completed' and r['retrieval_mode']!=mode for r in rows):
            raise ValueError('Fallback mislabeled as hybrid')
        results[mode]={**summarize_rows(rows),**rates(rows),
            'mean_mrr':sum(r.get('mrr',0) for r in rows)/120,
            'languages':{lang:rates([r for r in rows if r['language']==lang]) for lang in ('en','ko')},
            'peak_process_rss_bytes':max(m['peak_rss_bytes'] for m in memories),
            'peak_end_private_bytes':max(m['private_bytes'] for m in memories)}
        all_rows[mode]={(r['id'],r['repeat']):r for r in rows}
    differences=[]
    for case in frozen['cases']:
        a=all_rows['dense_fallback'][(case['id'],0)]
        b=all_rows['hybrid'][(case['id'],0)]
        if a.get('page_hit')!=b.get('page_hit'):
            differences.append({'id':case['id'],'dense_page_hit':a.get('page_hit'),
                'hybrid_page_hit':b.get('page_hit'),'acceptable_evidence':case.get('acceptable_evidence'),
                'dense_sources':a.get('sources'),'hybrid_sources':b.get('sources')})
    a,b=results['dense_fallback'],results['hybrid']
    page_delta=a['page_hit']-b['page_hit']
    failure_delta=a['failures']/120-b['failures']/120
    usable_coverage=min(a['completed'],b['completed'])>=100 and max(a['failures'],b['failures'])/120<=.02
    return {'scope':'live Pinecone retrieval using frozen cached Gemini query vectors; generation/judging blocked402',
        'identity':frozen['identity'],'unique_questions':40,'fact_groups':len({c['case_group'] for c in frozen['cases']}),
        'attempts_per_condition':120,'results':results,'page_hit_delta':page_delta,
        'excerpt_hit_delta':a['excerpt_hit']-b['excerpt_hit'],
        'retrieval_development_screen_passed':usable_coverage and page_delta>=-.05-1e-9 and failure_delta<=.02+1e-9,
        'answer_quality_comparison':None,'statistical_noninferiority_claim':False,
        'differences':differences}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,required=True)
    args=parser.parse_args();report=compare(args.folder)
    soak=args.folder/'memory-soak.json'
    if soak.exists():
        memory=json.loads(soak.read_text(encoding='utf8'))
        report['memory']={k:memory.get(k) for k in ('elapsed_seconds','attempts','failures','memory_errors','started_at_utc','ended_at_utc')}
        report['memory']['screen']=memory_gate(memory)
    (args.folder/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('differences','results')},ensure_ascii=False))
