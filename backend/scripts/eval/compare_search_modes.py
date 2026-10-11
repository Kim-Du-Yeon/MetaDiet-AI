"""Frozen local Dense/BM25/Hybrid comparison. No production writes or new embeddings."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval.run_full_recipe_comparison import dump, sha, pack_context, evidence_metrics, validate_gold
from scripts.eval.run_dimension_comparison import validate_matrix, validate_source
from app.rag.chunking import expand_context


def fuse(channels, k):
    if k < 1:
        raise ValueError('Positive candidate cap required')
    scores = {}
    for channel in channels:
        for rank, index in enumerate(dict.fromkeys(channel), 1):
            scores[index] = scores.get(index, 0.) + 1 / (60 + rank)
    return sorted(scores, key=lambda index: -scores[index])[:k]


def validate_vector_identity(identity, expected):
    if (identity.get('model') != 'gemini-embedding-2' or identity.get('base_dimension') != 3072
        or any(identity.get(key) != value for key, value in expected.items())):
        raise ValueError('Cached vectors do not match source, chunks, questions or embedding model')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from rank_bm25 import BM25Okapi
    from app.rag.retriever import kiwi_tokenize
    source = ROOT / 'artifacts/uniform-full-v1'
    vectors = ROOT / 'artifacts/dimension-full-dev-v1'
    dataset = ROOT.parent / 'docs/rag_experiments/gold_core40_v2.json'
    translations_path = ROOT / 'artifacts/retrieval-core40-strict-v2/report.json'
    cases = json.loads(dataset.read_text(encoding='utf8')); validate_gold(cases)
    translations = json.loads(translations_path.read_text(encoding='utf8'))['frozen_translations']
    validate_source(json.loads((source / 'parse-report.json').read_text(encoding='utf8')),
                    json.loads((source / 'parse-identity.json').read_text(encoding='utf8')))
    names = ('pypdf-recursive', 'docling-page')
    validate_vector_identity(json.loads((vectors / 'identity.json').read_text(encoding='utf8')),
        {'source_parse': sha(source / 'parse-identity.json'),
         'bundles': {n: sha(source / f'{n}.json') for n in names},
         'dataset': sha(dataset), 'translations': sha(translations_path)})
    identity = {'dataset': sha(dataset), 'translations': sha(translations_path), 'dimension': 3072,
        'source_identity': sha(source / 'parse-identity.json'), 'vector_identity': sha(vectors / 'identity.json'),
        'bundles': {n: sha(source / f'{n}.json') for n in names},
        'matrices': {n: sha(vectors / f'{n}-3072.npy') for n in names},
        'query_vectors': sha(vectors / 'queries3072.json'),
        'code': {p.name: sha(p) for p in (Path(__file__), ROOT / 'app/rag/chunking.py',
            ROOT / 'app/rag/retriever.py', ROOT / 'scripts/eval/run_full_recipe_comparison.py')},
        'candidate_k': 20, 'return_k': 4, 'context_chars': 6000, 'rrf_constant': 60}
    args.output.mkdir(parents=True, exist_ok=True)
    marker = args.output / 'identity.json'
    if marker.exists() and json.loads(marker.read_text(encoding='utf8')) != identity:
        raise ValueError('Changed experiment identity; use fresh output')
    dump(marker, identity)
    queries = json.loads((vectors / 'queries3072.json').read_text(encoding='utf8'))
    summary = {'scope': 'local exact cosine/BM25/two-stage RRF development retrieval; no answer quality',
        'n': len(cases), 'fact_groups': len({c['case_group'] for c in cases}), 'identity': identity, 'rows': []}
    for name in names:
        bundle = json.loads((source / f'{name}.json').read_text(encoding='utf8'))
        chunks = bundle['search_chunks']
        matrix = np.load(vectors / f'{name}-3072.npy'); validate_matrix(matrix, len(chunks), 3072)
        bm25 = BM25Okapi([kiwi_tokenize(c['text']) for c in chunks])
        for mode in ('dense', 'bm25', 'hybrid'):
            destination = args.output / f'{name}-{mode}'; rows = []
            for case in cases:
                started = time.perf_counter(); channels = []
                for query in dict.fromkeys((case['question'], translations[case['question']])):
                    q = np.asarray(queries[query]['vector'], dtype=np.float32)
                    validate_matrix(q[None, :], 1, 3072)
                    dense = list(map(int, np.argsort(-(matrix @ q), kind='stable')[:20])) if mode != 'bm25' else []
                    if mode != 'dense':
                        scores = bm25.get_scores(kiwi_tokenize(query))
                        sparse = [int(i) for i in np.argsort(-scores, kind='stable')[:20] if scores[i] > 0]
                    else:
                        sparse = []
                    channels.append(fuse([dense, sparse], 20))
                candidates = fuse(channels, 20)
                candidate_documents = [chunks[i] for i in candidates]
                context, delivered = pack_context(expand_context(bundle, [c['id'] for c in candidate_documents[:4]]), 6000)
                row = {**case, 'variant': 'none', 'repeat': 0, 'status': 'completed', 'mode': mode,
                    'recipe': name, 'seconds': time.perf_counter() - started,
                    **evidence_metrics(delivered, case), 'context': context,
                    'truncated': sum(c['context_truncated'] for c in delivered),
                    'documents': [{'text': c['text'], 'metadata': c['metadata']} for c in delivered],
                    'candidates': candidate_documents, 'translated': translations[case['question']]}
                dump(destination / f"none-0-{case['id']}.json", row); rows.append(row)
            result = {'recipe': name, 'mode': mode, 'n': len(rows),
                **{m: float(np.mean([r[m] for r in rows])) for m in ('page_hit', 'excerpt_hit', 'mrr', 'truncated')},
                'local_p95_ms': float(np.percentile([r['seconds'] * 1000 for r in rows], 95))}
            dump(destination / 'report.json', {'cases': rows, 'summary': result, 'identity': identity})
            summary['rows'].append(result); dump(args.output / 'report.json', summary)
            print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
