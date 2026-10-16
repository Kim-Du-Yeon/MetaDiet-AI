"""Local tokenizer equivalence, 100 frozen corpus excerpts per worker condition."""
import argparse
import ctypes
import hashlib
import json
import os
import pickle
import time
from pathlib import Path
from kiwipiepy import Kiwi

ROOT=Path(__file__).resolve().parents[3]


def memory():
    if os.name != 'nt':
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(name,ctypes.c_size_t) for name in
            ('peak','working','quota_peak_paged','quota_paged','quota_peak_nonpaged','quota_nonpaged','pagefile','peak_pagefile')]
    counters=Counters()
    counters.cb=ctypes.sizeof(counters)
    process=ctypes.windll.kernel32.GetCurrentProcess
    process.restype=ctypes.c_void_p
    assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(process()),ctypes.byref(counters),counters.cb)
    return counters.peak


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('condition',choices=['before','after']); args=parser.parse_args()
    folder=ROOT/'docs/coaching_review'
    path=folder/f'kiwi_{args.condition}100.json'
    assert not path.exists(), 'Do not overwrite evidence'
    docs=pickle.loads((ROOT/'backend/app/rag/release/chunks.pkl').read_bytes())
    cases=[docs[i*len(docs)//100].page_content for i in range(100)]
    report={'scope':'local Windows tokenizer equivalence; not Render RSS or RAG quality',
        'dataset_sha256':hashlib.sha256(json.dumps(cases,ensure_ascii=False).encode()).hexdigest(),'rows':[]}
    started=time.perf_counter()
    kiwi=Kiwi() if args.condition=='before' else Kiwi(num_workers=1)
    report['workers']=kiwi.num_workers
    for index,text in enumerate(cases):
        at=time.perf_counter()
        row={'index':index,'ok':False}
        try:
            tokens=[t.form for t in kiwi.tokenize(text)]
            row.update(ok=True,token_hash=hashlib.sha256(json.dumps(tokens,ensure_ascii=False).encode()).hexdigest())
        except Exception as exc:
            row['error_type']=type(exc).__name__
        row['elapsed_ms']=(time.perf_counter()-at)*1000
        report['rows'].append(row)
    report.update(total_ms=(time.perf_counter()-started)*1000,process_peak_bytes=memory())
    path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(args.condition,len(report['rows']),report['workers'],report['process_peak_bytes'],flush=True)


if __name__=='__main__':main()
