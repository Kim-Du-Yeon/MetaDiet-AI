"""Saved ag-013 evidence and synthetic retry fixtures; no provider I/O."""
import json
import pickle
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document
from app.rag.agentic import Assessment, bounded_retrieve, _scoped_context
from app.rag.neighbors import NeighborIndex


def test_korean_query_keeps_trailing_conditions_in_short_english_neighbor():
    meta={'source_file':'fiction.pdf','document_sha256':'fiction','page':1}
    anchor=Document(page_content='introduction', metadata=meta)
    text='background '*65+'Serving amount is 31 units for pilot adults, after recent training.'
    continuation=Document(page_content=text,metadata=meta)
    neighbor=NeighborIndex([anchor,continuation]).expand([anchor], '일회 권고와 조건')[0]
    assert neighbor.page_content == text
    _,packed=_scoped_context([anchor]+[Document(page_content='x'*1200) for _ in range(3)]+[neighbor])
    assert any('31 units' in d.page_content for d in packed)


@pytest.mark.asyncio
async def test_duplicate_rewrite_researches_missing_facts_once():
    doc=Document(page_content='verified partial fact')
    fetch=AsyncMock(return_value={'grounded':True,'max_score':.9,'docs':[doc]})
    assess=AsyncMock(side_effect=[
        Assessment(sufficient=False,missing_core=['fictional dose and scope'],rewrite='original'),
        Assessment(sufficient=True,missing_core=[],supported_excerpts=[doc.page_content])])
    value=await bounded_retrieve('original',retrieve=fetch,assess=assess,expand=AsyncMock(return_value=[]))
    assert value['agentic']['rounds']==2 and value['agentic']['stop_reason']=='sufficient'
    assert fetch.await_count==2
    assert fetch.await_args_list[1].args[0]=='original | fictional dose and scope'
    assert len(value['context'])<=6000


def test_saved_ag013_neighbor_recovery_preserves_original_offsets():
    root=Path(__file__).resolve().parents[3]
    saved=json.loads((root/'docs/agentic_rag/20261021-v13-final100/ag013-review.json').read_text(encoding='utf-8'))['attempt']
    docs=[Document(page_content=d['text'],metadata=d['metadata']) for d in saved['documents'][:4]]
    # Trusted packaged corpus only. No model, remote index or DB access.
    corpus=pickle.loads((root/'backend/app/rag/release/chunks.pkl').read_bytes())
    neighbors=NeighborIndex(corpus).expand(docs, 'ISSN의 1회 단백질 섭취 일반 권고와 개인별 적용 조건은 무엇인가?')
    context,packed=_scoped_context(docs+neighbors)
    assert len(context)<=6000
    matching=[d for d in packed if '0.25' in d.page_content and 'age and recent' in d.page_content]
    assert matching
    for d in matching:
        original=corpus[d.metadata['neighbor_chunk_index']].page_content
        assert d.page_content==original[d.metadata['excerpt_start']:d.metadata['excerpt_end']]
