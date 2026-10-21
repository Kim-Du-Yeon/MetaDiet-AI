"""Synthetic reproduction of ag-022's length error; no paid model calls."""
from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document
from pydantic import ValidationError

from app.rag.agentic import Assessment, bounded_retrieve


def test_complete_quote_over_240_characters_preserves_scope_and_exceptions():
    excerpt = 'Definition for fictional metric: ' + 'supported detail; ' * 20 + 'pilot only; equation unchanged.'
    value = Assessment(sufficient=True, missing_core=[], supported_excerpts=[excerpt])
    assert len(excerpt) > 240
    assert value.supported_excerpts == [excerpt]
    assert value.supported_excerpts[0].endswith('pilot only; equation unchanged.')


def test_quote_is_still_bounded_by_existing_evidence_budget():
    with pytest.raises(ValidationError):
        Assessment(sufficient=True, missing_core=[], supported_excerpts=['X' * 6001])
    with pytest.raises(ValidationError):
        Assessment(sufficient=True, missing_core=[], supported_excerpts=['x'] * 5)


@pytest.mark.asyncio
@pytest.mark.parametrize('verbatim', [True, False])
async def test_long_quote_does_not_bypass_body_verification(verbatim):
    body = 'Fictional definition: ' + 'bounded evidence; ' * 20 + 'restricted cohort only.'
    excerpt = body if verbatim else body + ' invented dose'
    value = await bounded_retrieve('definition and missing dose',
        retrieve=AsyncMock(return_value={'grounded': True, 'max_score': .9,
            'docs': [Document(page_content=body, metadata={'source_file': 'fictional.txt'})]}),
        assess=AsyncMock(return_value=Assessment(sufficient=False, missing_core=['dose'],
            rewrite='dose', supported_excerpts=[excerpt])), expand=AsyncMock(return_value=[]))
    assert value['grounded'] is verbatim
    if verbatim:
        assert body in value['answer_guidance']
        assert value['agentic']['answer_coverage'] == 'partial'
