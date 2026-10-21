"""Fictional development fixtures; no provider, DB or paid evaluation calls."""
from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document
from app.rag.agentic import Assessment, bounded_retrieve


@pytest.mark.asyncio
async def test_partial_evidence_survives_only_with_verified_excerpt():
    text = 'Pilot participants: metric Z is input minus output. No dose is specified.'
    fetch = AsyncMock(return_value={'grounded': True, 'context': text, 'max_score': .9,
        'docs': [Document(page_content=text, metadata={'source_file': 'fiction.pdf', 'page': 2})]})
    assess = AsyncMock(return_value=Assessment(sufficient=False, missing_core=['dose'],
        rewrite='metric Z dose', supported_excerpts=['metric Z is input minus output.'],
        definition_support='direct'))
    value = await bounded_retrieve('Define Z and state dose', retrieve=fetch, assess=assess,
        expand=AsyncMock(return_value=[]))
    assert value['grounded']
    assert value['agentic']['answer_coverage'] == 'partial'
    assert value['agentic']['missing_core'] == ['dose']
    assert 'dose' in value['answer_guidance']
    assert 'metric Z is input minus output.' in value['answer_guidance']
    assert fetch.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('grounded,excerpt', [(True, 'invented amount'), (False, 'known fact')])
async def test_partial_cannot_promote_unverified_or_low_score_evidence(grounded, excerpt):
    value = await bounded_retrieve('fact and dose',
        retrieve=AsyncMock(return_value={'grounded': grounded, 'context': 'known fact',
            'max_score': .1, 'docs': []}),
        assess=AsyncMock(return_value=Assessment(sufficient=False, missing_core=['dose'],
            supported_excerpts=[excerpt])))
    assert not value['grounded']


@pytest.mark.asyncio
async def test_complete_coverage_contract_reaches_answer_guidance():
    text = 'Metric Q: new measurements; equation unchanged from version A; pilot cohort only.'
    value = await bounded_retrieve('What changed and what stayed the same, for whom?',
        retrieve=AsyncMock(return_value={'grounded': True, 'context': text, 'max_score': .9,
            'docs': [Document(page_content=text, metadata={'source_file': 'fiction.pdf'})]}),
        assess=AsyncMock(return_value=Assessment(sufficient=True, missing_core=[],
            supported_excerpts=[text])), expand=AsyncMock(return_value=[]))
    assert text in value['answer_guidance']
    assert value['agentic']['answer_coverage'] == 'complete'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [OSError('offline error'), TimeoutError()])
async def test_operational_failure_cannot_reuse_previous_partial_assessment(failure):
    doc = Document(page_content='Known fictional fact.', metadata={'source_file': 'fiction.pdf'})
    value = await bounded_retrieve('fact and dose',
        retrieve=AsyncMock(side_effect=[{'grounded': True, 'context': doc.page_content,
            'max_score': .9, 'docs': [doc]}, failure]),
        assess=AsyncMock(return_value=Assessment(sufficient=False, missing_core=['dose'],
            rewrite='target dose', supported_excerpts=[doc.page_content])),
        expand=AsyncMock(return_value=[]))
    assert not value['grounded']
    assert value['agentic']['answer_coverage'] == 'none'
    assert 'answer_guidance' not in value


@pytest.mark.asyncio
@pytest.mark.parametrize('text', [
    '표: 가상 실험군만, 지표 A 8~12 단위; 일반인 적용 불가.',
    'Metric R: at least one cycle, not up to one cycle; exception: cohort B.',
    '2024 changed the fictional measurements; equation unchanged from 2020.',
])
async def test_material_qualifiers_are_not_removed_from_coverage_contract(text):
    value = await bounded_retrieve('Explain conditions and comparison',
        retrieve=AsyncMock(return_value={'grounded': True, 'context': text, 'max_score': .9,
            'docs': [Document(page_content=text, metadata={'source_file': 'fiction.pdf'})]}),
        assess=AsyncMock(return_value=Assessment(sufficient=True, missing_core=[],
            supported_excerpts=[text])), expand=AsyncMock(return_value=[]))
    assert text in value['answer_guidance']
