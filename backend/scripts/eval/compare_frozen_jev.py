"""Compare Jev with none on exact frozen local Hybrid candidates, bounded to 40 cases."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval.run_full_recipe_comparison import dump, sha, pack_context, evidence_metrics
from app.rag.chunking import expand_context
from app.rag.jev_reranker import rerank
from app.core.jev import JevClient
from app.agents.runtime import ExecutionBudget
from app.core.config import get_settings
from langchain_core.documents import Document
from langsmith import Client, tracing_context, traceable


def validate_candidates(bundle, rows, expected_hash, actual_hash):
    chunks = {c['id']: c for c in bundle['search_chunks']}
    if expected_hash != actual_hash or any(chunks.get(c['id']) != c for r in rows for c in r['candidates']):
        raise ValueError('Frozen candidate passages and current context bundle must match')


async def run(args):
    settings = get_settings()
    if not settings.typesafe_api_key:
        raise ValueError('TypeSafe key is required for a real Jev comparison')
    paths = sorted(args.directory.glob('none-0-*.json'))
    rows = [json.loads(p.read_text(encoding='utf8')) for p in paths]
    if (len(rows) != 40 or len({r['id'] for r in rows}) != 40
        or any(r['status'] != 'completed' or r['mode'] != 'hybrid' for r in rows)
        or len({r['recipe'] for r in rows}) != 1):
        raise ValueError('Require one completed frozen40 Hybrid candidate set')
    recipe = rows[0]['recipe']
    bundle_path = ROOT / 'artifacts/uniform-full-v1' / f'{recipe}.json'
    bundle = json.loads(bundle_path.read_text(encoding='utf8'))
    parent_identity = json.loads((args.directory / 'report.json').read_text(encoding='utf8'))['identity']
    validate_candidates(bundle, rows, parent_identity['bundles'][recipe], sha(bundle_path))
    identity = {'inputs': {p.name: sha(p) for p in paths}, 'bundle': sha(bundle_path),
        'model': settings.jev_model, 'candidate_k': 20, 'return_k': 4, 'context_chars': 6000,
        'code': {p.name: sha(p) for p in (Path(__file__), ROOT / 'app/core/jev.py',
            ROOT / 'app/rag/jev_reranker.py', ROOT / 'app/rag/chunking.py',
            ROOT / 'scripts/eval/run_full_recipe_comparison.py')}}
    marker = args.directory / 'jev-identity.json'
    if marker.exists() and json.loads(marker.read_text(encoding='utf8')) != identity:
        raise ValueError('Changed Jev comparison; use a fresh directory')
    dump(marker, identity)
    client = JevClient()
    tracer = Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint)
    results = []

    @traceable(name='jev-frozen-hybrid-rerank')
    async def one(row):
        documents = [Document(page_content=c['text'], metadata={**c['metadata'], 'frozen_chunk_id': c['id']})
                     for c in row['candidates']]
        started = time.perf_counter()
        result = await rerank(row['translated'], documents, client=client,
            budget=ExecutionBudget(max_model_calls=20, timeout_seconds=60), k=4)
        selected = [d.metadata['frozen_chunk_id'] for d in result['docs']]
        context, delivered = pack_context(expand_context(bundle, selected), 6000)
        return {**row, 'variant': 'jev', 'seconds': time.perf_counter() - started,
            'timing_scope': 'reranking and packing only; not end-to-end request',
            'events': result['events'], 'fallback_reason': result['fallback_reason'],
            **evidence_metrics(delivered, row), 'context': context,
            'truncated': sum(c['context_truncated'] for c in delivered),
            'documents': [{'text': c['text'], 'metadata': c['metadata']} for c in delivered]}

    with tracing_context(client=tracer, project_name=settings.langsmith_project,
                         enabled=settings.langsmith_tracing.lower() == 'true'):
        for row in rows:
            path = args.directory / f"jev-0-{row['id']}.json"
            result = json.loads(path.read_text(encoding='utf8')) if path.exists() else await one(row)
            dump(path, result); results.append(result)
            errors = {e['fallback_reason'] for e in result.get('events', []) if e.get('fallback_reason')}
            reasons = errors or {result.get('fallback_reason')}
            if result.get('fallback_reason') and not reasons <= set(args.allow_fallback):
                dump(args.directory / 'jev-failure.json', {'id': row['id'], 'errors': sorted(errors),
                    'fallback_reason': result['fallback_reason']})
                raise RuntimeError('Inspect Jev failure before permitting a diagnosed fallback')
            print(row['id'], 'jev', result['excerpt_hit'], result['fallback_reason'], flush=True)
    tracer.flush()
    dump(args.directory / 'jev-report.json', {'scope': 'development single-run shadow comparison; no adoption',
        'identity': identity, 'cases': results, 'n': len(results),
        'allowed_diagnosed_fallbacks': args.allow_fallback,
        'fallbacks': sum(bool(r.get('fallback_reason')) for r in results),
        'model_calls': sum(len(r['events']) for r in results),
        **{m: sum(r[m] for r in results) / len(results) for m in ('page_hit', 'excerpt_hit', 'mrr', 'seconds')}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--allow-fallback', nargs='*', default=[])
    asyncio.run(run(parser.parse_args()))
