import importlib.util
from pathlib import Path


def test_failed_attempts_remain_in_latency_and_freshness_denominators():
    path = Path(__file__).resolve().parents[2]/'scripts/eval/summarize_request_startup100.py'
    spec = importlib.util.spec_from_file_location('startup_summary', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = [{'index':i,'case':i%4,'status':'completed' if i<94 else 'failed',
        'total_ms':1 if i<94 else 180000, 'first_progress_ms':1 if i<99 else None,
        'fresh_numeric_match':i<94, 'answer':'', 'usage':{}} for i in range(100)]
    result = module.summarize({'rows':rows,'domain_unchanged':True})
    assert result['attempts'] == 100
    assert result['statuses']['failed'] == 6
    assert result['completion_all_attempts']['p95_ms'] == 180000
    assert result['first_progress']['missing'] == 1
    assert result['fresh_numeric_match'] == 94
