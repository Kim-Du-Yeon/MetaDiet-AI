import json
from pathlib import Path
import pytest
from scripts.eval.run_uniform_full_comparison import batches, collect_docling


def test_batches_cover_each_page_once():
    assert batches(5, 2) == [[1, 2], [3, 4], [5]]
    with pytest.raises(ValueError):
        batches(5, 0)


def test_collection_rejects_missing_or_duplicate_pages(tmp_path):
    with pytest.raises(ValueError, match='coverage'):
        collect_docling([], [1], {})


def test_collection_rejects_mixed_identity_before_reading_artifact(tmp_path):
    marker = tmp_path / 'part.json'
    marker.write_text(json.dumps({'status':'completed','pages':[1], 'identity':{'backend':'other'}}))
    with pytest.raises(ValueError, match='identity'):
        collect_docling([marker], [1], {'backend':'docling_parse'})

def test_collection_rejects_duplicate_pages(monkeypatch, tmp_path):
    import scripts.eval.run_uniform_full_comparison as module
    monkeypatch.setattr(module, 'validate_recovery_artifact', lambda row, pages: None)
    artifact=tmp_path/'artifact';artifact.mkdir()
    (artifact/'blocks.json').write_text(json.dumps({'blocks':[{'id':'one','pdf_page':1,'kind':'text','text':'a'}]}))
    markers=[]
    for number in range(2):
        p=tmp_path/f'{number}.json'
        p.write_text(json.dumps({'status':'completed','pages':[1],'identity':{},'artifact':str(artifact)}))
        markers.append(p)
    with pytest.raises(ValueError, match='coverage'):
        collect_docling(markers,[1],{})

def test_incomplete_completed_receipt_is_not_reusable():
    from scripts.eval.run_uniform_full_comparison import completed_receipt
    assert not completed_receipt({'status':'completed'})
    assert not completed_receipt({'status':'failed','artifact':'somewhere'})
    assert completed_receipt({'status':'completed','artifact':'somewhere'})
