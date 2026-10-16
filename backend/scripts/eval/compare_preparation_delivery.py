"""Synthetic delivery isolation: 100 identical lock waits per condition, no LLM/DB."""
import asyncio
import json
import statistics
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path

from app.db import thread_lock


async def main():
    root = Path(__file__).resolve().parents[3]
    source = subprocess.check_output(['git', 'show', 'ea2964b:backend/app/db/thread_lock.py'], cwd=root, text=True, encoding='utf-8')
    baseline = {}
    exec(compile(source, '<frozen-baseline>', 'exec'), baseline)
    @asynccontextmanager
    async def lock(*args):
        await asyncio.sleep(.02)
        yield
    baseline['conversation_lock'] = lock
    original = thread_lock.conversation_lock
    thread_lock.conversation_lock = lock
    async def factory():
        yield 'data: {"type":"completed","answer":"synthetic unchanged"}\n\n'
    reports = {}
    try:
        for label, implementation in [('before', baseline['serialized_stream']), ('after', thread_lock.serialized_stream)]:
            first, complete, failures, quality = [], [], 0, 0
            for _ in range(100):
                started = time.perf_counter()
                frames = []
                try:
                    async with asyncio.timeout(2):
                        async for frame in implementation(factory, 'synthetic', 'frozen-case'):
                            if not frames:
                                first.append((time.perf_counter() - started) * 1000)
                            frames.append(json.loads(frame.removeprefix('data: ')))
                    quality += frames[-1].get('answer') == 'synthetic unchanged'
                except Exception:
                    failures += 1
                complete.append((time.perf_counter() - started) * 1000)
            def metrics(values):
                return {'median_ms': round(statistics.median(values), 3), 'p95_ms': round(sorted(values)[94], 3)}
            reports[label] = {'attempts': 100, 'failures_timeouts': failures, 'unchanged_terminal': quality,
                'first_frame': metrics(first), 'completion': metrics(complete)}
    finally:
        thread_lock.conversation_lock = original
    report = {'scope': 'synthetic 20ms lock only; not public model latency, quality or fresh-record evidence',
        'baseline': 'ea2964b', 'results': reports}
    path = root / 'docs/food_catalog/PREPARATION_DELIVERY_SYNTHETIC.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
