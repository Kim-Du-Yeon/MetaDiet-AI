"""Uniform full-document parser/chunking comparison, isolated from live indexes.

On a worker failure stop for diagnosis; explicit reruns reuse verified batches.
No automatic backend/config substitution or unbounded native retries.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval.run_controlled_parser_comparison import (
    DOCLING_CONFIG, PARSERS, STRATEGIES, assemble, evaluate, runtime_environment,
    runtime_versions, validate_artifact, validate_runtime,
)
from scripts.eval.run_full_recipe_comparison import dump, sha, validate_gold
from scripts.eval.run_docling_recovery import validate_recovery_artifact


def batches(count, size):
    if count < 1 or size < 1:
        raise ValueError('Positive page count and batch size required')
    return [list(range(p, min(p + size, count + 1))) for p in range(1, count + 1, size)]


def completed_receipt(result):
    return bool(result and result.get('status') == 'completed' and result.get('artifact'))


def collect_docling(markers, expected_pages, identity):
    blocks, pages = [], []
    for path in sorted(markers):
        row = json.loads(path.read_text(encoding='utf8'))
        if row.get('status') != 'completed' or row.get('identity') != identity:
            raise ValueError('Docling batch identity/status mismatch')
        validate_recovery_artifact(row, row['pages'])
        subset = json.loads((Path(row['artifact']) / 'blocks.json').read_text(encoding='utf8'))['blocks']
        blocks.extend({**b, 'id': f"batch-{row['pages'][0]}:{b['id']}"} for b in subset)
        pages.extend(row['pages'])
    if sorted(pages) != expected_pages or len(pages) != len(set(pages)):
        raise ValueError('Docling full page coverage missing or duplicated')
    return blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--batch-pages', type=int, default=24)
    ap.add_argument('--stage', choices=['parse', 'evaluate', 'all'], default='all')
    ap.add_argument('--manifest', type=Path, default=ROOT.parent / 'docs/nutrition/corpus_manifest.json')
    ap.add_argument('--dataset', type=Path, default=ROOT.parent / 'docs/rag_experiments/gold_core40_v2.json')
    ap.add_argument('--anchors', type=Path, default=ROOT.parent / 'docs/rag_experiments/parser_preservation_v1.json')
    ap.add_argument('--translations', type=Path, default=ROOT / 'artifacts/retrieval-core40-strict-v2/report.json')
    args = ap.parse_args()
    args.output = args.output.resolve()
    os.environ.update(runtime_environment(ROOT))
    from pypdf import PdfReader
    sources = json.loads(args.manifest.read_text(encoding='utf8'))
    cases = json.loads(args.dataset.read_text(encoding='utf8')); validate_gold(cases)
    anchors = json.loads(args.anchors.read_text(encoding='utf8'))
    pages = {e['path']: list(range(1, len(PdfReader(args.manifest.parent / e['path']).pages) + 1)) for e in sources}
    versions = runtime_versions()
    identity = {'sources': {e['path']: sha(args.manifest.parent / e['path']) for e in sources},
                'pages': pages, 'runtime_versions': versions, 'config': DOCLING_CONFIG,
                'batch_pages': args.batch_pages, 'python': sys.version,
                'code': {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / 'app/rag/ingestion.py',
                    ROOT / 'scripts/eval/run_docling_recovery.py', ROOT / 'scripts/eval/compare_rag_recipes.py']}}
    marker = args.output / 'parse-identity.json'
    if marker.exists() and json.loads(marker.read_text(encoding='utf8')) != identity:
        raise ValueError('Full parse identity changed; use a new directory')
    dump(marker, identity)
    report = {'scope': 'full corpus uniform parser config; no production activation', 'parsers': [],
              'pages': pages, 'total_pages': sum(map(len, pages.values()))}
    if args.stage in ('parse', 'all'):
        from scripts.eval.compare_rag_recipes import parse_worker
        for parser in PARSERS:
            for entry in sources:
                folder = args.output / 'workers' / parser / Path(entry['path']).stem
                result_path = folder / 'controlled-result.json'
                expected = {'sha256': identity['sources'][entry['path']], 'parser': parser, 'pages': pages[entry['path']],
                    'code': sha(ROOT / 'app/rag/ingestion.py'), 'parser_version': versions[parser],
                    'backend': 'docling_parse', 'config': DOCLING_CONFIG}
                source = {**entry, 'path': str((args.manifest.parent / entry['path']).resolve())}
                result = json.loads(result_path.read_text(encoding='utf8')) if result_path.exists() else None
                if not completed_receipt(result):
                    if parser == 'docling':
                        job = {'source': source, 'output': str(folder), 'backend': 'docling_parse',
                               'config': DOCLING_CONFIG, 'ranges': batches(len(pages[entry['path']]), args.batch_pages),
                               'gpu_runtime': True, 'wall_timeout': 1800}
                        job_path = folder / 'input-job.json'; dump(job_path, job)
                        started = time.perf_counter()
                        with (folder / 'parent.log').open('w', encoding='utf8') as log:
                            process = subprocess.run([sys.executable, str(ROOT / 'scripts/eval/run_docling_recovery.py'),
                                                      '--job', str(job_path)], stdout=log, stderr=log)
                        execution = json.loads((folder / 'execution.json').read_text(encoding='utf8'))
                        result = {'status': execution['status'], 'exit_code': process.returncode,
                                  'elapsed_seconds': time.perf_counter() - started, 'execution': str(folder / 'execution.json')}
                        if process.returncode:
                            dump(result_path, result)
                            dump(args.output / 'failure.json', {'parser': parser, 'source': entry['path'], **result})
                            raise RuntimeError(f'Inspect failure logs before retry: {folder}')
                        validate_runtime(execution['identity']['runtime_versions'], versions)
                        blocks = collect_docling(list((folder / 'results').glob('*.json')), pages[entry['path']], execution['identity'])
                        artifact = folder / 'collected'; result['artifact'] = str(artifact)
                        dump(artifact / 'blocks.json', {'blocks': blocks})
                        dump(artifact / 'manifest.json', {'sha256': expected['sha256'], 'parser': parser,
                            'parser_version': versions[parser], 'selected_pages': expected['pages'],
                            'ingestion_code_sha256': expected['code'],
                            'effective_config': {'ocr': False, 'docling_backend': expected['backend'], 'docling_config': DOCLING_CONFIG},
                            'derived_collection': True, 'part_markers': [str(p) for p in sorted((folder / 'results').glob('*.json'))]})
                    else:
                        result = parse_worker(source, parser, pages[entry['path']], folder, 900)
                        result = {k: v for k, v in result.items() if k not in {'blocks', 'manifest'}}
                        if result['status'] != 'completed':
                            dump(result_path, result)
                            dump(args.output / 'failure.json', {'parser': parser, 'source': entry['path'], **result})
                            raise RuntimeError(f'Inspect failure logs before retry: {folder}')
                artifact = Path(result['artifact'])
                manifest = json.loads((artifact / 'manifest.json').read_text(encoding='utf8'))
                validate_artifact(manifest, expected)
                if parser == 'docling':
                    execution = json.loads((folder / 'execution.json').read_text(encoding='utf8'))
                    validate_runtime(execution['identity']['runtime_versions'], versions)
                    collect_docling(list((folder / 'results').glob('*.json')), expected['pages'], execution['identity'])
                dump(result_path, result)
                report['parsers'].append({'parser': parser, 'source_file': entry['path'], **result})
                dump(args.output / 'controlled-parse-report.json', report)
                print(f"full parse {parser} {entry['path']} completed {len(expected['pages'])} pages", flush=True)
    else:
        report = json.loads((args.output / 'controlled-parse-report.json').read_text(encoding='utf8'))
    if args.stage in ('evaluate', 'all'):
        recipes = assemble(args, sources, pages, report, cases, anchors)
        if len(recipes) != len(PARSERS) * len(STRATEGIES):
            raise ValueError('Incomplete full comparison matrix')
        eval_identity = {'parse_identity': sha(marker), 'dataset': sha(args.dataset), 'anchors': sha(args.anchors),
                         'translations': sha(args.translations), 'helpers': {str(p.relative_to(ROOT)): sha(p) for p in [
                            ROOT / 'app/rag/chunking.py', ROOT / 'scripts/eval/run_controlled_parser_comparison.py',
                            ROOT / 'scripts/eval/run_full_recipe_comparison.py', ROOT / 'scripts/eval/audit_full_recipe_parsing.py',
                            ROOT / 'app/rag/retriever.py']}}
        dump(args.output / 'evaluation-identity.json', eval_identity)
        evaluate(args, recipes, cases)
        for filename in ('parse-report.json', 'retrieval-report.json'):
            path = args.output / filename; value = json.loads(path.read_text(encoding='utf8'))
            value['scope'] = 'uniform full corpus development comparison; BM25 only, not final answer quality'
            dump(path, value)


if __name__ == '__main__':
    main()
