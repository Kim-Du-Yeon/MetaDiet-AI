"""Non-production RAG experiment safety, metrics and Windows memory accounting."""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
_job = None


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate_frozen(bundle):
    cases, translations = bundle.get('cases', []), bundle.get('translations', {})
    if len(cases) != 40 or len({c['id'] for c in cases}) != 40:
        raise ValueError('Expected frozen development40')
    if any(c.get('review_status') != 'reviewed' or c.get('split') != 'development'
           or not translations.get(c['question']) for c in cases):
        raise ValueError('Unreviewed case or missing frozen translation')
    if bundle.get('identity') != digest({'cases':cases, 'translations':translations}):
        raise ValueError('Frozen input identity mismatch')


def isolated_settings(values):
    from app.core.config import Settings
    # Explicit values override even inherited environment; no production DB client.
    return Settings(_env_file=None, gemini_api_key=values['GEMINI_API_KEY'],
        pinecone_api_key=values['PINECONE_API_KEY'],
        gemini_model=values.get('GEMINI_MODEL') or 'gemini-3.8-flash',
        gemini_eval_model=values.get('GEMINI_EVAL_MODEL') or 'gemini-3.1-pro-preview',
        pinecone_index_name='diet-agent-rag',
        pinecone_namespace='metadiet-gemini-1157903c493dbb5d759f',
        embedding_model='gemini-embedding-2', embedding_dimension=3072,
        rag_chunks_path=str(ROOT/'backend/app/rag/release/chunks.pkl'),
        rag_use_rerank=False, rag_score_threshold=.35, rag_candidate_k=20,
        supabase_url='https://disabled.invalid', supabase_service_key='validation-disabled',
        supabase_jwt_secret='validation-disabled', supabase_db_url='',
        langsmith_tracing='false', langsmith_api_key='', model_max_retries=0,
        model_timeout_seconds=30, eval_model_timeout_seconds=90)


def configure(env_path: Path):
    from dotenv import dotenv_values
    values=dotenv_values(env_path)
    allowed={'GEMINI_API_KEY','PINECONE_API_KEY','GEMINI_MODEL','GEMINI_EVAL_MODEL'}
    if set(values)-allowed or not all(values.get(k) for k in ('GEMINI_API_KEY','PINECONE_API_KEY')):
        raise ValueError('Validation env must contain only allowlisted provider settings')
    for key in list(os.environ):
        if key.startswith(('SUPABASE_', 'LANGSMITH_', 'LANGCHAIN_')) or key == 'GOOGLE_API_KEY':
            os.environ.pop(key)
    os.environ.update(LANGSMITH_TRACING='false', LANGCHAIN_TRACING_V2='false')
    settings=isolated_settings(values)
    import app.core.config as config
    config.get_settings=lambda:settings
    # Fail closed if future evaluator edits import a write-capable application layer.
    class DenyDatabaseImports:
        def find_spec(self, fullname, path=None, target=None):
            if fullname.startswith(('app.db', 'app.api', 'app.agents', 'supabase', 'psycopg')):
                raise RuntimeError('Database/Agent imports prohibited in RAG validation')
    sys.meta_path.insert(0,DenyDatabaseImports())
    return settings


def percentile(values, p):
    if not values:
        return None
    ordered=sorted(values)
    return ordered[max(0, math.ceil(len(ordered)*p)-1)]


def summarize_rows(rows):
    n=len(rows)
    completed=[r for r in rows if r.get('status')=='completed']
    def rate(predicate):
        return sum(bool(predicate(r)) for r in rows)/n if n else None
    return {'attempts':n, 'completed':len(completed), 'failures':n-len(completed),
        'page_hit_rate':rate(lambda r:r.get('status')=='completed' and r.get('page_hit')),
        'supported_correct_rate':rate(lambda r:r.get('judge',{}).get('supported') is True and r.get('judge',{}).get('correct') is True) if any('judge' in r for r in rows) else None,
        'judge_coverage':rate(lambda r:r.get('judge',{}).get('supported') in (True,False)),
        'grounded_rate':rate(lambda r:r.get('grounded')),
        'completed_p50_seconds':percentile([r['seconds'] for r in completed],.5),
        'completed_p95_seconds':percentile([r['seconds'] for r in completed],.95),
        'all_attempt_p95_seconds':percentile([r['seconds'] for r in rows],.95)}


def memory_gate(report):
    samples=report.get('samples',[])
    warmed=[s for s in samples if s['elapsed_seconds']>=300]
    first=[s['private_bytes'] for s in warmed if s['elapsed_seconds']<1200]
    last=[s['private_bytes'] for s in warmed if s['elapsed_seconds']>=report.get('elapsed_seconds',0)-900]
    growth=statistics.median(last)-statistics.median(first) if first and last else None
    limit=512*1024**2
    gates={'duration':report.get('elapsed_seconds',0)>=7200,
        'workload':report.get('attempts',0)>=600,
        'failure_rate':report.get('failures',0)/max(1,report.get('attempts',0))<=.01,
        'sample_coverage':len(samples)>=300 and len(first)>=30 and len(last)>=30,
        'headroom':bool(samples) and max(s['private_bytes'] for s in samples)<limit*.9,
        'warmed_growth':growth is not None and growth<=32*1024**2,
        'no_local_tokenizer':bool(samples) and all(not s['kiwi_loaded'] and not s['bm25_loaded'] for s in samples),
        'no_memory_errors':not report.get('memory_errors',0)}
    return {'passed':all(gates.values()),'gates':gates,'warmed_private_growth_bytes':growth}


def memory_snapshot():
    if os.name != 'nt':
        raise RuntimeError('This runner requires Windows memory counters; Linux needs cgroup measurements')
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(name,ctypes.c_size_t) for name in
            ('peak','rss','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
    counters=Counters(); counters.cb=ctypes.sizeof(counters)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    if not ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo(
            ctypes.c_void_p(kernel.GetCurrentProcess()),ctypes.byref(counters),counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'rss_bytes':counters.rss,'peak_rss_bytes':counters.peak,'private_bytes':counters.private}


def enforce_windows_commit_limit(mebibytes):
    """Actual process private-commit cap, NOT a Linux RSS/cgroup emulation."""
    global _job
    if os.name != 'nt':
        raise RuntimeError('Windows Job Object required')
    from ctypes import wintypes as w
    size=ctypes.c_size_t
    class Basic(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
            ('flags',w.DWORD),('min_ws',size),('max_ws',size),('active',w.DWORD),
            ('affinity',size),('priority',w.DWORD),('scheduling',w.DWORD)]
    class IO(ctypes.Structure):
        _fields_=[(name,ctypes.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
    class Extended(ctypes.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_limit',size),('job_limit',size),('peak_process',size),('peak_job',size)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.restype=w.HANDLE
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR]
    kernel.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
    kernel.GetCurrentProcess.restype=w.HANDLE
    job=kernel.CreateJobObjectW(None,None)
    info=Extended();info.basic.flags=0x100;info.process_limit=mebibytes*1024**2
    if not job or not kernel.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(job,kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
    _job=job
