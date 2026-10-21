"""Offline diagnostics must explain rejection without exposing evidence."""
import json
from unittest.mock import AsyncMock
import pytest
from langchain_core.documents import Document
from app.rag.agentic import Assessment, bounded_retrieve
from app.rag.evidence_spans import diagnose_excerpt


def test_numeric_boundary_is_distinct_from_text_mismatch():
    assert diagnose_excerpt('10 mg', '110 mg')['reason'] == 'numeric_boundary_or_token_mismatch'
    assert diagnose_excerpt('1 0 mg', '10 mg')['reason'] == 'numeric_boundary_or_token_mismatch'


def test_mismatch_offset_has_no_source_text():
    result = diagnose_excerpt('Secret value 20 mg.', 'Secret value 10 mg.')
    assert result['reason'] == 'text_mismatch'
    assert result['common_prefix_chars'] == 11
    assert result['excerpt_offset'] == 13
    assert result['body_offset'] == 13
    assert 'Secret' not in json.dumps(result)


def test_whitespace_success_and_empty():
    assert diagnose_excerpt('a b', 'a\nb')['reason'] == 'matched'
    assert diagnose_excerpt('  ', 'anything')['reason'] == 'empty_excerpt'
    assert diagnose_excerpt('word', '')['reason'] == 'text_mismatch'


@pytest.mark.asyncio
async def test_failed_quote_retains_diagnostics_after_evidence_is_cleared(caplog):
    result = await bounded_retrieve('dose',
        retrieve=AsyncMock(return_value={'grounded': True, 'max_score': .9,
            'docs': [Document(page_content='Private dose 10 mg.')] }),
        assess=AsyncMock(return_value=Assessment(sufficient=True, missing_core=[],
            supported_excerpts=['Private dose 20 mg.'])), expand=AsyncMock(return_value=[]))
    assert result['agentic']['stop_reason'] == 'excerpt_mismatch'
    assert not result['grounded'] and result['docs'] == []
    failure = result['agentic']['excerpt_failures'][0]
    assert failure['quote_index'] == 0
    assert failure['documents'][0]['document_index'] == 0
    assert failure['documents'][0]['reason'] == 'text_mismatch'
    assert 'rag_excerpt_verification' in caplog.text
    assert 'Private' not in caplog.text
    assert 'Private' not in json.dumps(failure)


def test_saved_whitespace_failure_remains_accepted_without_provider_io():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    saved = json.loads((root/'docs/agentic_rag/20261021-ag022-recheck/single-attempt.json').read_text(encoding='utf-8'))
    rows = [json.loads(line) for line in (root/'docs/agentic_rag/20261021-batch-live-validation/matched100/attempts.jsonl').read_text(encoding='utf-8').splitlines()]
    row = next(r for r in rows if r['attempt_id'] == 'ag-022' and r['condition'] == 'agentic')
    quote = saved['decision']['supported_excerpts'][0]
    assert any(diagnose_excerpt(quote, d['text'])['reason'] == 'matched' for d in row['documents'][:4])
