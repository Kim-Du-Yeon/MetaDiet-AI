"""Whitespace-only verification, including saved ag-022, without provider I/O."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document

from app.rag.evidence_spans import find_excerpt_span
from app.rag.agentic import Assessment, bounded_retrieve


@pytest.mark.parametrize('body,quote', [
    ('head: the  value\r\nis\tstable. tail', 'the value is stable.'),
    ('E s t i m a t e d  E n e r g y', 'Estimated Energy'),
    ('값은\u00a0 20 g입니다.', '값은 20 g입니다.'),
    ('단위는 m g 이며 값은 20입니다.', '단위는 mg이며 값은 20입니다.'),
])
def test_whitespace_only_match_maps_to_original_span(body, quote):
    span = find_excerpt_span(quote, body)
    assert span is not None
    selected = body[span[0]:span[1]]
    assert ''.join(selected.split()) == ''.join(quote.split())


@pytest.mark.parametrize('body,quote', [
    ('Dose is 10 mg.', 'Dose is 20 mg.'),
    ('Dose is 10 mg.', 'Dose is 10 g.'),
    ('Dose is 10 mg.', 'Dose equals 10 mg.'),
    ('Only adults.', 'only adults.'),
    ('Range is 10–20.', 'Range is 10-20.'),
    ('Value is 1 0 mg.', 'Value is 10 mg.'),
    ('Value is 10 mg.', 'Value is 1 0 mg.'),
    ('Value is 1 . 0 mg.', 'Value is 1.0 mg.'),
    ('Value is 110 mg.', '10 mg.'),
    ('Value is 1.0 mg.', '1'),
    ('Value is 1e3 mg.', '3 mg.'),
    ('１２ mg', '12 mg'),
    ('ab\u200bcd', 'abcd'),
    ('anything', ' \n\t'),
])
def test_rewriting_numbers_units_and_nonwhitespace_changes_are_rejected(body, quote):
    assert find_excerpt_span(quote, body) is None


def test_saved_ag022_quote_resolves_to_original_body():
    root = Path(__file__).resolve().parents[3]
    saved = json.loads((root/'docs/agentic_rag/20261021-ag022-recheck/single-attempt.json').read_text(encoding='utf-8'))
    quote = saved['decision']['supported_excerpts'][0]
    rows = (json.loads(line) for line in (root/'docs/agentic_rag/20261021-batch-live-validation/matched100/attempts.jsonl').read_text(encoding='utf-8').splitlines())
    row = next(r for r in rows if r['attempt_id']=='ag-022' and r['condition']=='agentic')
    assert not any(quote in d['text'] for d in row['documents'][:4])
    assert any(find_excerpt_span(quote, d['text']) is not None for d in row['documents'][:4])


@pytest.mark.asyncio
async def test_saved_ag022_definition_needs_reassessment_despite_matching_quote():
    root = Path(__file__).resolve().parents[3]
    saved = json.loads((root/'docs/agentic_rag/20261021-ag022-recheck/single-attempt.json').read_text(encoding='utf-8'))
    rows = (json.loads(line) for line in (root/'docs/agentic_rag/20261021-batch-live-validation/matched100/attempts.jsonl').read_text(encoding='utf-8').splitlines())
    row = next(r for r in rows if r['attempt_id']=='ag-022' and r['condition']=='agentic')
    cases = json.loads((root/'docs/agentic_rag/20261021-batch-live-validation/matched100/cases.json').read_text(encoding='utf-8'))
    question = next(c['question'] for c in cases if c['attempt_id']=='ag-022')
    docs = [Document(page_content=d['text'],metadata=d['metadata']) for d in row['documents'][:4]]
    fetch = AsyncMock(return_value={'grounded':True,'max_score':0,'docs':docs})
    assess = AsyncMock(return_value=Assessment.model_validate(saved['decision']))
    result = await bounded_retrieve(question,retrieve=fetch,assess=assess,expand=AsyncMock(return_value=[]))
    assert not result['grounded']
    assert result['agentic']['answer_coverage'] == 'none'
    assert result['agentic']['rejected_excerpts'] == 0
    assert fetch.await_count == assess.await_count == 2
    assert result['agentic']['definition_research_required']
    # The old decision has no definition classification; quote identity still passes.
    quote = saved['decision']['supported_excerpts'][0]
    assert any(find_excerpt_span(quote, doc.page_content) is not None for doc in docs)


@pytest.mark.asyncio
async def test_partial_answer_contains_original_span_and_document_reference():
    body = 'Fictional scope: p i l o t\n only; 10 mg.'
    doc = Document(page_content=body, metadata={'source_file':'fiction.txt', 'page':3})
    result = await bounded_retrieve('scope and missing time',
        retrieve=AsyncMock(return_value={'grounded':True,'max_score':.9,'docs':[doc]}),
        assess=AsyncMock(return_value=Assessment(sufficient=False,missing_core=['time'],
            supported_excerpts=['pilot only; 10 mg.'])), expand=AsyncMock(return_value=[]))
    assert result['grounded']
    span = result['agentic']['excerpt_spans'][0]
    assert span['document_index'] == 0
    assert span['source'] == 'fiction.txt' and span['page'] == 3
    assert body[span['start']:span['end']] == 'p i l o t\n only; 10 mg.'
    assert json.dumps('p i l o t\n only; 10 mg.')[1:-1] in result['answer_guidance']


@pytest.mark.asyncio
@pytest.mark.parametrize('sufficient', [True,False])
async def test_unverified_claim_cannot_be_promoted_even_with_a_valid_other_quote(sufficient):
    doc = Document(page_content='Dose is 10 mg. Pilot only.',metadata={'source_file':'fiction.txt'})
    result = await bounded_retrieve('dose and scope',
        retrieve=AsyncMock(return_value={'grounded':True,'max_score':.9,'docs':[doc]}),
        assess=AsyncMock(return_value=Assessment(sufficient=sufficient,
            missing_core=[] if sufficient else ['time'], supported_excerpts=['Pilot only.','Dose is 20 mg.'])),
        expand=AsyncMock(return_value=[]))
    assert not result['grounded']
    assert result['agentic']['stop_reason'] == 'excerpt_mismatch'
    assert not result['context']


@pytest.mark.asyncio
async def test_quote_cannot_be_assembled_across_documents():
    docs=[Document(page_content=part,metadata={'source_file':str(i)})
          for i,part in enumerate(['Dose is','10 mg.'])]
    result=await bounded_retrieve('dose',
        retrieve=AsyncMock(return_value={'grounded':True,'max_score':.9,'docs':docs}),
        assess=AsyncMock(return_value=Assessment(sufficient=True,missing_core=[],
            supported_excerpts=['Dose is 10 mg.'])),expand=AsyncMock(return_value=[]))
    assert not result['grounded']
