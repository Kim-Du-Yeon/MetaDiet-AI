"""Bounded full-corpus dimension ablation; no live index or .env mutation.

Gemini Embedding 2 MRL prefix projection is API-verified on document/query
probes before cached 3072 vectors are reused. Costs are not inferred from dims.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval.run_full_recipe_comparison import dump, sha, pack_context, evidence_metrics, validate_gold
from scripts.eval.run_controlled_parser_comparison import runtime_environment, DOCLING_CONFIG, PARSERS, STRATEGIES, validate_artifact
from app.rag.chunking import expand_context

DIMENSIONS = (768, 1536, 3072)


def validate_cases(cases, split):
    if split == 'development':
        validate_gold(cases)
    elif (split != 'heldout' or not cases or len({c['id'] for c in cases}) != len(cases)
          or any(c.get('split') != split or c.get('review_status') != 'reviewed' for c in cases)):
        raise ValueError('Requires unique reviewed cases in the explicit evaluation split')


def validate_source(report, identity):
    expected = {(p, s) for p in PARSERS for s in STRATEGIES}
    recipes = [(r['parser'], r['chunking']) for r in report.get('recipes', [])]
    pages = identity.get('pages', {})
    if (set(recipes) != expected or len(recipes) != len(expected) or report.get('excluded') != []
        or identity.get('config') != DOCLING_CONFIG or len(pages) != 10
        or set(pages) != set(identity.get('sources', {}))
        or not identity.get('runtime_versions') or not identity.get('code')
        or any(not ps or ps != list(range(1, len(ps) + 1)) for ps in pages.values())):
        raise ValueError('Uniform full source matrix/config/page provenance required')


def validate_matrix(matrix, count, dimension):
    if (matrix.shape != (count, dimension) or not np.isfinite(matrix).all()
        or not np.allclose(np.linalg.norm(matrix, axis=1), 1., atol=1e-4)):
        raise ValueError('Invalid vector cache shape, finite values or normalization')


def project_vectors(matrix, dimension):
    if matrix.ndim != 2 or dimension < 1 or dimension > matrix.shape[1] or not np.isfinite(matrix).all():
        raise ValueError('Invalid projection input')
    rows = matrix[:, :dimension].astype(np.float32, copy=True)
    norm = np.linalg.norm(rows, axis=1, keepdims=True)
    if np.any(norm == 0):
        raise ValueError('Zero prefix cannot be normalized')
    return rows / norm


def verify_api_projection(output):
    from app.core.config import get_settings
    from app.core.embeddings import GeminiEmbeddings
    settings = get_settings()
    if settings.embedding_model != 'gemini-embedding-2' or settings.embedding_dimension != 3072:
        raise ValueError('This experiment requires Gemini Embedding 2, base 3072')
    embedder = GeminiEmbeddings()
    probes = ['title: none | text: 성인의 단백질 섭취는 활동 수준과 적용 조건에 따라 달라집니다.',
              'task: search result | query: What does the guideline recommend for adult protein intake?']
    identity = {'model': settings.embedding_model, 'code': sha(ROOT / 'app/core/embeddings.py'), 'probes': probes}
    marker = output / 'projection-api-verification.json'
    if marker.exists():
        row = json.loads(marker.read_text(encoding='utf8'))
        if row['identity'] != identity or not row['passed']:
            raise ValueError('API projection verification identity/result mismatch')
        return row
    checks = []
    try:
        for probe in probes:
            vectors = {}
            for dimension in DIMENSIONS:
                settings.embedding_dimension = dimension
                started = time.perf_counter()
                vectors[dimension] = np.asarray(embedder._embed(probe), dtype=np.float32)
                checks.append({'probe_type': probe.split(':')[0], 'dimension': dimension,
                               'api_seconds': time.perf_counter() - started})
            for dimension in DIMENSIONS[:-1]:
                projected = project_vectors(vectors[3072][None, :], dimension)[0]
                cosine = float(projected @ vectors[dimension])
                checks.append({'probe_type': probe.split(':')[0], 'dimension': dimension, 'prefix_cosine': cosine})
        passed = all(x['prefix_cosine'] >= .9999 for x in checks if 'prefix_cosine' in x)
        row = {'identity': identity, 'checks': checks, 'passed': passed,
               'method': '3072 prefix projection and unit normalization; actual API 768/1536 probe validation',
               'source': 'https://ai.google.dev/gemini-api/docs/embeddings'}
        dump(marker, row)
        if not passed:
            raise ValueError('API projection mismatch; do not infer lower-dimension vectors')
        return row
    finally:
        settings.embedding_dimension = 3072


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True, help='Completed uniform full comparison directory')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--recipes', nargs='+', required=True, help='At most two fixed parser-chunking names')
    ap.add_argument('--dataset', type=Path, default=ROOT.parent / 'docs/rag_experiments/gold_core40_v2.json')
    ap.add_argument('--translations', type=Path, default=ROOT / 'artifacts/retrieval-core40-strict-v2/report.json')
    ap.add_argument('--split', choices=('development', 'heldout'), default='development')
    args = ap.parse_args()
    if not 1 <= len(args.recipes) <= 2 or len(set(args.recipes)) != len(args.recipes):
        ap.error('Freeze one or two unique candidate recipes')
    os.environ.update(runtime_environment(ROOT))
    args.output.mkdir(parents=True, exist_ok=True)
    from app.core.config import get_settings
    from app.core.embeddings import GeminiEmbeddings
    settings = get_settings()
    source_report = json.loads((args.source / 'parse-report.json').read_text(encoding='utf8'))
    source_identity = json.loads((args.source / 'parse-identity.json').read_text(encoding='utf8'))
    validate_source(source_report, source_identity)
    parse_report = json.loads((args.source / 'controlled-parse-report.json').read_text(encoding='utf8'))
    rows = parse_report['parsers']
    expected_pairs = {(p, s) for p in PARSERS for s in source_identity['pages']}
    if (len(rows) != len(expected_pairs) or {(r['parser'], r['source_file']) for r in rows} != expected_pairs
        or any(r.get('status') != 'completed' for r in rows)):
        raise ValueError('Complete full parse receipts required')
    for row in rows:
        manifest = json.loads((Path(row['artifact']) / 'manifest.json').read_text(encoding='utf8'))
        source_code = {k.replace('\\', '/'): v for k, v in source_identity['code'].items()}
        validate_artifact(manifest, {'sha256': source_identity['sources'][row['source_file']],
            'parser': row['parser'], 'pages': source_identity['pages'][row['source_file']],
            'code': source_code['app/rag/ingestion.py'],
            'parser_version': source_identity['runtime_versions'][row['parser']],
            'backend': 'docling_parse', 'config': DOCLING_CONFIG})
    permitted = {f"{r['parser']}-{r['chunking']}" for r in source_report['recipes']}
    if not set(args.recipes) <= permitted or source_report.get('excluded'):
        raise ValueError('Candidates require complete uniform full comparison')
    cases = json.loads(args.dataset.read_text(encoding='utf8')); validate_cases(cases, args.split)
    translations = json.loads(args.translations.read_text(encoding='utf8'))['frozen_translations']
    bundles = {name: json.loads((args.source / f'{name}.json').read_text(encoding='utf8')) for name in args.recipes}
    identity = {'model': settings.embedding_model, 'base_dimension': 3072, 'dimensions': DIMENSIONS,
        'method': 'API-verified MRL prefix projection', 'source_parse': sha(args.source / 'parse-identity.json'),
        'bundles': {name: sha(args.source / f'{name}.json') for name in args.recipes},
        'dataset': sha(args.dataset), 'translations': sha(args.translations), 'split': args.split,
        'code': {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / 'app/core/embeddings.py',
            ROOT / 'app/rag/chunking.py', ROOT / 'scripts/eval/run_full_recipe_comparison.py']}}
    # Round-trip JSON so tuple/list identity does not reject a valid resume.
    identity = json.loads(json.dumps(identity))
    marker = args.output / 'identity.json'
    if marker.exists() and json.loads(marker.read_text(encoding='utf8')) != identity:
        raise ValueError('Dimension experiment settings changed; use a fresh directory')
    dump(marker, identity)
    verification = verify_api_projection(args.output)
    embedding = GeminiEmbeddings()
    queries = sorted({q for case in cases for q in (case['question'], translations[case['question']])})
    query_path = args.output / 'queries3072.json'
    cached = json.loads(query_path.read_text(encoding='utf8')) if query_path.exists() else {}
    for q in queries:
        if q not in cached:
            started = time.perf_counter(); vector = embedding.embed_query(q)
            cached[q] = {'vector': vector, 'api_seconds': time.perf_counter() - started}
            dump(query_path, cached)
    query_matrix = np.asarray([cached[q]['vector'] for q in queries], dtype=np.float32)
    validate_matrix(query_matrix, len(queries), 3072)
    report = {'scope': f'full corpus dense-only {args.split} dimension evaluation; not final Ragas answer quality',
        'identity': identity, 'api_verification': verification, 'candidate_k': 20, 'return_k': 4,
        'context_budget': 6000, 'repeats': 3, 'reranker': None,
        'timing_scope': 'exact cosine local retrieval only; query API probe/cached construction reported separately; not request p95',
        'cost_scope': 'dimension truncation reduces vector bytes, not input-token embedding API price', 'recipes': []}
    for name, bundle in bundles.items():
        chunks = bundle['search_chunks']; matrix_path = args.output / f'{name}-3072.npy'
        started = time.perf_counter()
        if matrix_path.exists():
            matrix = np.load(matrix_path)
        else:
            rows = []
            for start in range(0, len(chunks), 32):
                rows.extend(embedding.embed_documents([c['text'] for c in chunks[start:start + 32]]))
                print(f"dimension base embed {name} {min(start+32,len(chunks))}/{len(chunks)}", flush=True)
            matrix = np.asarray(rows, dtype=np.float32)
            np.save(matrix_path, matrix)
        validate_matrix(matrix, len(chunks), 3072)
        construction_seconds = time.perf_counter() - started
        for dimension in DIMENSIONS:
            vectors = project_vectors(matrix, dimension)
            queries_d = project_vectors(query_matrix, dimension)
            np.save(args.output / f'{name}-{dimension}.npy', vectors)
            by_query = {q: queries_d[i] for i, q in enumerate(queries)}
            samples = []
            for repeat in range(3):
                for case in cases:
                    started = time.perf_counter()
                    ranks = {}
                    for q in dict.fromkeys((case['question'], translations[case['question']])):
                        order = np.argsort(-(vectors @ by_query[q]), kind='stable')[:20]
                        for rank, i in enumerate(order, 1):
                            ranks[int(i)] = ranks.get(int(i), 0) + 1 / (60 + rank)
                    selected = sorted(ranks, key=lambda i: -ranks[i])[:4]
                    context, delivered = pack_context(expand_context(bundle, [chunks[i]['id'] for i in selected]), 6000)
                    samples.append({**case, 'repeat': repeat, **evidence_metrics(delivered, case),
                        'actual_prompt_context': context, 'context_chars': len(context),
                        'retrieved_contexts': [c['text'] for c in delivered], 'context_metadata': [c['metadata'] for c in delivered],
                        'truncated': sum(c['context_truncated'] for c in delivered), 'local_seconds': time.perf_counter() - started})
            destination = args.output / f'{name}-{dimension}-contexts.json'; dump(destination, samples)
            summary = {'recipe': name, 'dimension': dimension, 'n_unique': len(cases), 'fact_groups': len({c.get('case_group',c['id']) for c in cases}),
                'n_runs': len(samples), 'vectors': len(chunks), 'matrix_bytes': vectors.nbytes,
                'construction_seconds': construction_seconds, 'samples': str(destination),
                **{m: float(np.mean([s[m] for s in samples])) for m in ('page_hit','excerpt_hit','mrr','context_chars','truncated')},
                'local_p50_ms': float(np.percentile([s['local_seconds']*1000 for s in samples],50)),
                'local_p95_ms': float(np.percentile([s['local_seconds']*1000 for s in samples],95))}
            report['recipes'].append(summary); dump(args.output / 'report.json', report)
            print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
