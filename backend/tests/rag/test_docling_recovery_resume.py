import json
from pathlib import Path

from scripts.eval.run_docling_recovery import valid_cached_range


def test_incomplete_or_corrupt_cached_range_is_not_reused(tmp_path):
    marker = tmp_path / 'result.json'
    job = {'identity': {'source_sha256': 'source', 'ingestion_code': 'code',
                       'backend': 'docling_parse', 'config': {'device': 'cuda'},
                       'runtime_versions': {'docling': 'test'}}}
    marker.write_text('{broken', encoding='utf8')
    assert not valid_cached_range(marker, job, [1, 2])
    artifact = tmp_path / 'parse'
    artifact.mkdir()
    manifest = {'sha256': 'source', 'ingestion_code_sha256': 'code', 'parser': 'docling',
                'parser_version': 'test', 'selected_pages': [1, 2],
                'effective_config': {'docling_backend': 'docling_parse', 'docling_config': {'device': 'cuda'}}}
    (artifact / 'manifest.json').write_text(json.dumps(manifest))
    marker.write_text(json.dumps({'status': 'completed', 'identity': job['identity'], 'artifact': str(artifact)}))
    (artifact / 'document.json').write_text(json.dumps({'documents': [{'pages': {'1': {}}}]}))
    assert not valid_cached_range(marker, job, [1, 2])
    (artifact / 'document.json').write_text(json.dumps({'documents': [{'pages': {'1': {}, '2': {}}}]}))
    assert valid_cached_range(marker, job, [1, 2])
    assert not valid_cached_range(marker, {'identity': {'run': 2}}, [1, 2])
    manifest['sha256'] = 'another-source'
    (artifact / 'manifest.json').write_text(json.dumps(manifest))
    assert not valid_cached_range(marker, job, [1, 2])
