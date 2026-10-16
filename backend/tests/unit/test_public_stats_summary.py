import importlib.util
import sys
from pathlib import Path


def test_missing_stats_are_failures_even_with_successful_answers():
    folder = Path(__file__).resolve().parents[2]/'scripts/eval'
    sys.path.insert(0, str(folder))
    try:
        spec = importlib.util.spec_from_file_location('stats_summary', folder/'summarize_public_stats100.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = [{'index':i, 'case':i%4, 'status':'completed', 'answer':'', 'usage':{},
            'total_ms':1, 'fresh_numeric_match':True, 'stage_timings_ms':{'public_stats':1},
            'public_stats':{'today_calories':0,'target_calories':1800} if i<98 else {}}
            for i in range(100)]
        result = module.summary({'rows':rows, 'domain_unchanged':True, 'expected':[0,1800]})
        assert result['stats_correct'] == 98
        assert result['stats_missing_or_wrong'] == 2
        assert result['attempts'] == 100
    finally:
        sys.path.remove(str(folder))


def test_freshness_latency_keeps_all_failures_in_denominator():
    folder = Path(__file__).resolve().parents[2]/'scripts/eval'
    sys.path.insert(0, str(folder))
    try:
        spec = importlib.util.spec_from_file_location('stats_summary', folder/'summarize_public_stats100.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = [{'index':i,'correct':i<84,'total_ms':1 if i<84 else 40000,
                 **({'error_type':'RuntimeError'} if i>=97 else {'stats_available':i<84})}
                for i in range(100)]
        result = module.freshness_summary({'rows':rows,'restored_original_values':True})
        assert result['attempts'] == 100 and result['correct'] == 84
        assert result['request_errors'] == 3 and result['stats_missing'] == 13
        assert result['p95_ms'] == 40000
    finally:
        sys.path.remove(str(folder))
