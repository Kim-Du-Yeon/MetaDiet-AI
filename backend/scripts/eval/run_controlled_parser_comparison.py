"""Controlled parser/chunking development probe; never activates a live index."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.rag.chunking import ChunkConfig, chunk_blocks, expand_context
from scripts.eval.run_full_recipe_comparison import dump, sha, validate_gold, pack_context, evidence_metrics, normalized

PARSERS = ('pypdf', 'pdfplumber', 'docling')
STRATEGIES = ('page', 'parent_child', 'section', 'recursive')
DOCLING_CONFIG = dict(timeout_seconds=300, num_threads=4, parser_threads=1, device='cuda', table_structure=True,
                      table_mode='accurate', batch_size=4, queue_size=100, picture_images=True)


def runtime_environment(root):
    folders = {'TEMP': root / 'artifacts/runtime-temp', 'TMP': root / 'artifacts/runtime-temp',
               'TMPDIR': root / 'artifacts/runtime-temp', 'PIP_CACHE_DIR': root / 'artifacts/pip-cache',
               'HF_HOME': root / 'artifacts/model-cache'}
    for path in folders.values():
        path.mkdir(parents=True, exist_ok=True)
    return {key: str(path.resolve()) for key, path in folders.items()}


def select_pages(sources, selections, cases, anchors):
    result = {s['path']: set(selections[s['path']]) for s in sources}
    if set(result) != set(selections):
        raise ValueError('Page selections and corpus differ')
    for case in cases:
        result[case['gold_source']].add(case['gold_page'])
        for evidence in case.get('acceptable_evidence', []):
            result[evidence['source']].update(evidence['pdf_pages'])
    for anchor in anchors['text_anchors'] + anchors['table_rows']:
        result[anchor['source']].add(anchor['page'])
    if any(not pages or any(isinstance(p, bool) or not isinstance(p, int) or p < 1 for p in pages) for pages in result.values()):
        raise ValueError('Page numbers must be positive integers')
    return {source: sorted(pages) for source, pages in result.items()}


def validate_artifact(manifest, expected):
    config = manifest.get('effective_config', {})
    if (manifest.get('sha256') != expected['sha256'] or manifest.get('parser') != expected['parser']
        or manifest.get('selected_pages') != expected['pages'] or manifest.get('ingestion_code_sha256') != expected['code']
        or config.get('ocr') is not False):
        raise ValueError('Controlled parse source/page/code/config mismatch')
    if expected.get('parser_version') and manifest.get('parser_version') != expected['parser_version']:
        raise ValueError('Controlled parser version mismatch')
    if expected['parser'] == 'docling' and (config.get('docling_backend') != expected['backend']
        or config.get('docling_config') != expected['config']):
        raise ValueError('Controlled Docling backend/config mismatch')


def completed_cache(path):
    try:
        row = json.loads(path.read_text(encoding='utf8'))
        return row if isinstance(row, dict) and row.get('status') == 'completed' else None
    except (OSError, ValueError, TypeError):
        return None


def validate_runtime(donor, current):
    keys = {'torch', 'torchvision', 'docling', 'docling-core', 'docling-parse',
            'docling-ibm-models', 'pypdfium2', 'transformers'}
    if not donor or any(current.get(k) != v for k, v in donor.items() if k in keys):
        raise ValueError('Donor parse runtime differs or is unrecorded')
    if any(k in current and k not in donor for k in keys):
        raise ValueError('Donor parse runtime is incomplete')


def runtime_versions():
    from importlib.metadata import distributions
    names = {'pypdf', 'pdfplumber', 'docling', 'docling-core', 'docling-parse', 'docling-ibm-models',
             'torch', 'torchvision', 'transformers', 'pypdfium2', 'kiwipiepy', 'rank-bm25', 'langchain-text-splitters'}
    versions = {}
    paths = [ROOT / 'artifacts/gpu-runtime', ROOT / 'artifacts/parser-runtime', ROOT / 'venv/Lib/site-packages']
    for path in paths:
        for item in distributions(path=[str(path)]):
            name = item.metadata['Name'].lower().replace('_', '-')
            if name in names:
                versions.setdefault(name, item.version)
    return versions


def recursive_bundle(blocks, metadata):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150)
    pages = chunk_blocks(blocks, metadata, ChunkConfig(strategy='page'))
    chunks = []
    for page in pages['search_chunks']:
        for position, text in enumerate(splitter.split_text(page['text'])):
            identifier = hashlib.sha256((page['id'] + str(position) + text + 'recursive-1200-150').encode()).hexdigest()
            chunks.append({'id': identifier, 'text': text, 'metadata': {**page['metadata'], 'strategy': 'recursive',
                           'recipe_id': 'recursive-1200-150'}})
    return {'search_chunks': chunks, 'parents': {}, 'recipe': {'strategy': 'recursive', 'max_chars': 1200, 'overlap': 150}}


def build_bundle(blocks, metadata, strategy):
    # A selected-page probe must not join sections across omitted source pages.
    runs = []
    for page in sorted({b['pdf_page'] for b in blocks}):
        if runs and page == runs[-1][-1] + 1:
            runs[-1].append(page)
        else:
            runs.append([page])
    combined = {'search_chunks': [], 'parents': {}}
    for pages in runs:
        group = [b for b in blocks if b['pdf_page'] in pages]
        part = recursive_bundle(group, metadata) if strategy == 'recursive' else chunk_blocks(group, metadata, ChunkConfig(strategy=strategy))
        combined['search_chunks'].extend(part['search_chunks'])
        combined['parents'].update(part['parents'])
    return combined


def parse_stage(args, sources, pages):
    from scripts.eval.compare_rag_recipes import parse_worker
    report = {'scope': 'selected development pages, not full corpus retrieval', 'pages': pages, 'parsers': []}
    versions = runtime_versions()
    for parser in PARSERS:
        for entry in sources:
            source = {**entry, 'path': str((args.manifest.parent / entry['path']).resolve())}
            folder = args.output / 'workers' / parser / Path(entry['path']).stem
            result_path = folder / 'controlled-result.json'
            expected = {'sha256': sha(Path(source['path'])), 'parser': parser, 'pages': pages[entry['path']],
                        'code': sha(ROOT / 'app/rag/ingestion.py'), 'backend': 'docling_parse', 'config': DOCLING_CONFIG,
                        'parser_version': versions[parser]}
            cached_path = result_path
            if args.reuse_parses and not result_path.exists():
                cached_path = args.reuse_parses / 'workers' / parser / Path(entry['path']).stem / 'controlled-result.json'
            result = completed_cache(cached_path)
            if result is not None:
                if cached_path != result_path:
                    if parser == 'docling':
                        markers = list((cached_path.parent / 'results').glob('*.json'))
                        if len(markers) != 1:
                            raise ValueError('Donor runtime marker missing or ambiguous')
                        marker = json.loads(markers[0].read_text(encoding='utf8'))
                        validate_runtime(marker.get('identity', {}).get('runtime_versions', {}), versions)
                    result = {**result, 'reused_from': str(cached_path)}
            else:
                if result_path.exists():
                    from uuid import uuid4
                    import shutil
                    history = folder / 'controlled-history' / uuid4().hex
                    history.mkdir(parents=True)
                    shutil.copy2(result_path, history / 'controlled-result.json')
            if result is None and parser == 'docling':
                folder.mkdir(parents=True, exist_ok=True)
                job = folder / 'input-job.json'
                dump(job, {'source': source, 'output': str(folder), 'backend': 'docling_parse', 'config': DOCLING_CONFIG,
                           'ranges': [pages[entry['path']]], 'gpu_runtime': True, 'wall_timeout': 600})
                start = time.perf_counter()
                with (folder / 'parent.log').open('w', encoding='utf8') as log:
                    process = subprocess.run([sys.executable, str(ROOT / 'scripts/eval/run_docling_recovery.py'), '--job', str(job)], stdout=log, stderr=log)
                execution = json.loads((folder / 'execution.json').read_text(encoding='utf8'))
                markers = list((folder / 'results').glob('*.json'))
                result = {'status': execution['status'], 'exit_code': process.returncode, 'elapsed_seconds': time.perf_counter() - start}
                if process.returncode == 0 and len(markers) == 1:
                    result['artifact'] = json.loads(markers[0].read_text(encoding='utf8'))['artifact']
                dump(result_path, result)
            elif result is None:
                result = parse_worker(source, parser, pages[entry['path']], folder, 180)
                result = {k: v for k, v in result.items() if k not in {'blocks', 'manifest'}}
                dump(result_path, result)
            if result['status'] == 'completed':
                artifact = Path(result['artifact'])
                manifest = json.loads((artifact / 'manifest.json').read_text(encoding='utf8'))
                validate_artifact(manifest, expected)
                if parser == 'docling':
                    from scripts.eval.run_full_recipe_comparison import validate_cached_docling_pages
                    validate_cached_docling_pages(artifact, expected['pages'])
                result['parser_version'] = manifest['parser_version']
                dump(result_path, result)
            report['parsers'].append({'parser': parser, 'source_file': entry['path'], **result})
            dump(args.output / 'controlled-parse-report.json', report)
            print(f"{parser} {entry['path']} {result['status']}", flush=True)
    return report


def assemble(args, sources, pages, report, cases, anchors):
    complete = []
    preservation = []
    for parser in PARSERS:
        rows = [r for r in report['parsers'] if r['parser'] == parser]
        if len(rows) != len(sources) or any(r['status'] != 'completed' for r in rows):
            continue
        bundles = {s: {'search_chunks': [], 'parents': {}} for s in STRATEGIES}
        blocks_by_source = {}
        for entry in sources:
            row = next(r for r in rows if r['source_file'] == entry['path'])
            blocks = json.loads((Path(row['artifact']) / 'blocks.json').read_text(encoding='utf8'))['blocks']
            if any(b['pdf_page'] not in pages[entry['path']] for b in blocks):
                raise ValueError('Unexpected parsed page')
            blocks_by_source[entry['path']] = blocks
            metadata = {**entry, 'source_file': entry['path'], 'sha256': sha(args.manifest.parent / entry['path']), 'parser': parser}
            for strategy in STRATEGIES:
                bundle = build_bundle(blocks, metadata, strategy)
                bundles[strategy]['search_chunks'].extend(bundle['search_chunks'])
                bundles[strategy]['parents'].update(bundle['parents'])
        from scripts.eval.audit_full_recipe_parsing import row_preserved
        checks = []
        for anchor in anchors['text_anchors']:
            text = normalized('\n'.join(b['text'] for b in blocks_by_source[anchor['source']] if b['pdf_page'] == anchor['page']))
            checks.append({'id': anchor['id'], 'type': 'text_anchor', 'passed': all(normalized(t) in text for t in anchor['terms'])})
        for anchor in anchors['table_rows']:
            blocks = [b for b in blocks_by_source[anchor['source']] if b['pdf_page'] == anchor['page']]
            checks.append({'id': anchor['id'], 'type': 'table_row', 'passed': row_preserved(blocks, anchor)})
        for group in sorted({c.get('case_group', c['id']) for c in cases}):
            case = next(c for c in cases if c.get('case_group', c['id']) == group)
            evidence = case.get('acceptable_evidence') or [{'source': case['gold_source'], 'pdf_pages': [case['gold_page']]}]
            passed = any(normalized(case['gold_excerpt']) in normalized('\n'.join(b['text'] for b in blocks_by_source[e['source']] if b['pdf_page'] in e['pdf_pages'])) for e in evidence)
            checks.append({'id': group, 'type': 'gold_excerpt', 'passed': passed})
        preservation.append({'parser': parser, 'checks': checks, 'totals': {kind: {'passed': sum(c['passed'] for c in checks if c['type'] == kind), 'n': sum(c['type'] == kind for c in checks)} for kind in ('text_anchor', 'table_row', 'gold_excerpt')},
                             'tables': sum(b['kind'] == 'table' for blocks in blocks_by_source.values() for b in blocks),
                             'images': sum(b['kind'] == 'image' for blocks in blocks_by_source.values() for b in blocks)})
        for strategy, bundle in bundles.items():
            path = args.output / f'{parser}-{strategy}.json'
            dump(path, bundle)
            complete.append({'parser': parser, 'chunking': strategy, 'bundle': str(path), 'search_chunks': len(bundle['search_chunks'])})
    included = {r['parser'] for r in complete}
    dump(args.output / 'parse-report.json', {'scope': 'same selected pages; native parser pool=1; Docling GPU, other parsers CPU',
                                           'recipes': complete, 'excluded': [p for p in PARSERS if p not in included]})
    dump(args.output / 'preservation-report.json', preservation)
    return complete


def evaluate(args, recipes, cases):
    import numpy as np
    from rank_bm25 import BM25Okapi
    from app.rag.retriever import kiwi_tokenize
    translations = json.loads(args.translations.read_text(encoding='utf8'))['frozen_translations']
    report = {'scope': 'BM25 development probe on selected pages; not final RAG or answer quality', 'n': len(cases),
              'fact_groups': len({c.get('case_group', c['id']) for c in cases}), 'candidate_k': 20, 'return_k': 4,
              'dataset_sha256': sha(args.dataset), 'translations_sha256': sha(args.translations), 'recipes': []}
    for recipe in recipes:
        bundle = json.loads(Path(recipe['bundle']).read_text(encoding='utf8')); chunks = bundle['search_chunks']
        index = BM25Okapi([kiwi_tokenize(c['text']) for c in chunks])
        samples = []
        for case in cases:
            fused = {}
            for query in dict.fromkeys([case['question'], translations[case['question']]]):
                scores = index.get_scores(kiwi_tokenize(query))
                order = [int(i) for i in np.argsort(-scores, kind='stable')[:20] if scores[i] > 0]
                for rank, i in enumerate(order, 1):
                    fused[i] = fused.get(i, 0) + 1 / (60 + rank)
            hits = sorted(fused, key=lambda i: -fused[i])[:4]
            expanded = expand_context(bundle, [chunks[i]['id'] for i in hits])
            for budget in (6000, 12000):
                context, delivered = pack_context(expanded, budget)
                samples.append({**case, 'context_budget': budget, **evidence_metrics(delivered, case), 'actual_prompt_context': context,
                                'context_chars': len(context), 'truncated': sum(c['context_truncated'] for c in delivered),
                                'retrieved_contexts': [c['text'] for c in delivered], 'context_metadata': [c['metadata'] for c in delivered]})
        path = args.output / f"{recipe['parser']}-{recipe['chunking']}-contexts.json"; dump(path, samples)
        for budget in (6000, 12000):
            selected = [s for s in samples if s['context_budget'] == budget]
            summary = {**recipe, 'context_budget': budget, 'contexts': str(path), **{m: sum(s[m] for s in selected) / len(selected) for m in ('page_hit', 'excerpt_hit', 'mrr', 'context_chars', 'truncated')}}
            report['recipes'].append(summary)
            print(json.dumps({k: v for k, v in summary.items() if k not in {'contexts', 'bundle'}}, ensure_ascii=False), flush=True)
    dump(args.output / 'retrieval-report.json', report)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--manifest', type=Path, default=ROOT.parent / 'docs/nutrition/corpus_manifest.json')
    p.add_argument('--dataset', type=Path, default=ROOT.parent / 'docs/rag_experiments/gold_core40_v2.json')
    p.add_argument('--selections', type=Path, default=ROOT.parent / 'docs/rag_experiments/parser_pages.json')
    p.add_argument('--anchors', type=Path, default=ROOT.parent / 'docs/rag_experiments/parser_preservation_v1.json')
    p.add_argument('--translations', type=Path, default=ROOT / 'artifacts/retrieval-core40-strict-v2/report.json')
    p.add_argument('--reuse-parses', type=Path, help='Reuse only independently validated completed artifacts; recompute chunks/metrics')
    args = p.parse_args(); os.environ.update(runtime_environment(ROOT)); args.output.mkdir(parents=True, exist_ok=True)
    sources = json.loads(args.manifest.read_text(encoding='utf8')); cases = json.loads(args.dataset.read_text(encoding='utf8')); validate_gold(cases)
    anchors = json.loads(args.anchors.read_text(encoding='utf8'))
    pages = select_pages(sources, json.loads(args.selections.read_text(encoding='utf8')), cases, anchors)
    identity = {'manifest': sha(args.manifest), 'dataset': sha(args.dataset), 'anchors': sha(args.anchors), 'translations': sha(args.translations),
                'sources': {s['path']: sha(args.manifest.parent / s['path']) for s in sources}, 'pages': pages,
                'runner': sha(Path(__file__)), 'ingestion': sha(ROOT / 'app/rag/ingestion.py'), 'docling_config': DOCLING_CONFIG,
                'runtime_versions': runtime_versions(), 'python': sys.version,
                'helper_hashes': {str(path.relative_to(ROOT)): sha(path) for path in [ROOT / 'app/rag/chunking.py',
                    ROOT / 'app/rag/retriever.py', ROOT / 'scripts/eval/run_full_recipe_comparison.py',
                    ROOT / 'scripts/eval/compare_rag_recipes.py', ROOT / 'scripts/eval/audit_full_recipe_parsing.py',
                    ROOT / 'scripts/eval/run_docling_recovery.py']}}
    old = args.output / 'identity.json'
    if old.exists() and json.loads(old.read_text(encoding='utf8')) != identity:
        raise ValueError('Experiment identity differs; use a fresh directory')
    dump(old, identity)
    report = parse_stage(args, sources, pages)
    recipes = assemble(args, sources, pages, report, cases, anchors)
    if len(recipes) != len(PARSERS) * len(STRATEGIES):
        if recipes:
            evaluate(args, recipes, cases)
        raise RuntimeError('Complete requested parser matrix unavailable; see explicit exclusions')
    evaluate(args, recipes, cases)


if __name__ == '__main__':
    main()
