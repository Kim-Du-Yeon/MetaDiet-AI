"""Document-ID selection cannot paraphrase evidence or escape assessed context."""
import pytest
from langchain_core.documents import Document
from app.rag.agentic import resolve_document_assessment, _scoped_context


def test_selected_original_pdf_text_is_never_model_rewritten():
    docs = [Document(page_content='Dose is <10%\n for p i l o t only. — footnote')]
    result = resolve_document_assessment({'sufficient':True,'missing_core':[],
        'supported_document_indices':[0]},docs)
    assert result.supported_excerpts == [docs[0].page_content]


@pytest.mark.parametrize('indices', [[1],[-1],[True],[0,0],[8],['0']])
def test_invalid_ids_fail_closed(indices):
    with pytest.raises(ValueError):
        resolve_document_assessment({'sufficient':True,'missing_core':[],
            'supported_document_indices':indices},[Document(page_content='original')])


def test_ids_use_exact_scoped_truncated_documents():
    context,docs = _scoped_context([Document(page_content='A'*7000)])
    result = resolve_document_assessment({'sufficient':True,'missing_core':[],
        'supported_document_indices':[0]},docs)
    assert len(context)<=6000
    assert '[문서 ID: 0,' in context
    assert result.supported_excerpts == [docs[0].page_content]
    assert len(result.supported_excerpts[0]) < 6000


def test_saved_ag000_success_has_exact_source_spans_and_complete_usage():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    rows = [json.loads(line) for line in (root/'docs/agentic_rag/20261021-document-id-smoke/attempts.jsonl').read_text(encoding='utf-8').splitlines()]
    row = next(r for r in rows if r['attempt_id']=='ag-000' and r['condition']=='agentic')
    assert row['status']=='completed' and row['cost_complete']
    assert row['answer_finish_reason']=='STOP'
    assert row['agentic']['rejected_excerpts']==0
    assert row['agentic']['answer_coverage']=='complete'
    assert row['agentic']['excerpt_spans']
    assert all(s['match_kind']=='exact' and s['start']==0 and s['end']>0
               for s in row['agentic']['excerpt_spans'])
    # Source-reviewed gold's required distinctions, not a model quality score.
    assert '10%' in row['answer'] and 'strong recommendation' in row['answer']
    assert '성인' in row['answer'] and '어린이' in row['answer']
