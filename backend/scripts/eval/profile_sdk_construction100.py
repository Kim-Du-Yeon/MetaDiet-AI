"""100+100 local SDK construction only; synthetic key, zero network calls."""
import asyncio
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core import llm
from summarize_latency100 import distribution


async def main():
    llm.get_settings = lambda: SimpleNamespace(gemini_api_key='synthetic-profile-only',
        gemini_model='gemini-3.8-flash', gemini_vision_model='gemini-3.8-flash',
        gemini_eval_model='gemini-3.8-flash', model_timeout_seconds=30,
        eval_model_timeout_seconds=90, model_max_retries=0)
    rows = []
    try:
        for reused in (False, True):
            if reused:
                llm.get_chat_model(reuse_provider=True, thinking_level='low').prepare()
            for i in range(100):
                started = time.perf_counter()
                model = llm.get_chat_model(reuse_provider=reused, thinking_level='low')
                model.prepare()
                rows.append({'condition': 'reuse' if reused else 'fresh', 'index': i,
                             'prepare_ms': (time.perf_counter()-started)*1000})
                if not reused:
                    await model._provider.aclose()
    finally:
        await llm.close_shared_model_client()
    result = {'scope': 'local_sdk_construction_only_no_network_synthetic_key', 'rows': rows,
        'summary': {mode: distribution([r['prepare_ms'] for r in rows if r['condition'] == mode])
                    for mode in ('fresh', 'reuse')},
        'limitations': 'Local setup only; excludes remote generation, does not establish public latency improvement.'}
    path = ROOT / 'docs/sdk_phase_public/local_preparation100.json'
    assert not path.exists(), 'Do not overwrite evidence'
    path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__': asyncio.run(main())
