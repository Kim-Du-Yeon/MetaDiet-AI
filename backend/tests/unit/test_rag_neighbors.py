from langchain_core.documents import Document
import pytest


def doc(text, page=1, source='reference.pdf', digest='build-document'):
    return Document(page_content=text, metadata={'source_file':source,'page':page,
                    'document_sha256':digest,'embedding_model':'test','embedding_dimension':3})


def test_neighbors_follow_exact_anchor_and_preserve_scope_and_offsets():
    from app.rag.neighbors import NeighborIndex
    anchor=doc('introduction to metric Z')
    neighbor=doc('background '*90+'Metric Z is 42 units for pilot participants only.')
    index=NeighborIndex([anchor,neighbor,doc('other file',source='other.pdf')])
    found=index.expand([anchor], 'What is metric Z?', limit=2)
    assert len(found)==1 and '42 units' in found[0].page_content
    start,end=found[0].metadata['excerpt_start'],found[0].metadata['excerpt_end']
    assert found[0].page_content==neighbor.page_content[start:end]
    assert len(found[0].page_content)<=700
    assert found[0].metadata['document_sha256']=='build-document'
    assert not index.expand([doc('not indexed')], 'metric Z')


def test_neighbors_reject_other_document_revision_or_distant_page():
    from app.rag.neighbors import NeighborIndex
    anchor=doc('anchor')
    index=NeighborIndex([doc('wrong revision',digest='old'),anchor,doc('far away',page=7)])
    assert index.expand([anchor], 'far away')==[]


def test_neighbor_limit_and_originals_are_never_returned():
    from app.rag.neighbors import NeighborIndex
    docs=[doc('same source line '+str(i)) for i in range(7)]
    index=NeighborIndex(docs)
    result=index.expand([docs[1],docs[3],docs[5]], 'line',limit=2)
    assert len(result)==2
    assert not {d.page_content for d in result}&{d.page_content for d in docs[1::2]}
    with pytest.raises(ValueError):index.expand([docs[1]],'line',limit=5)


def test_neighbor_excerpt_covers_specific_terms_even_after_generic_intro():
    from app.rag.neighbors import NeighborIndex
    anchor=doc('intro')
    text='balance '+'background '*90+'Marker Z concentration is 42 units, balanced with indicator W.'
    result=NeighborIndex([anchor,doc(text)]).expand([anchor],'balance marker concentration')
    assert '42 units' in result[0].page_content


@pytest.mark.asyncio
async def test_loop_only_expands_qualified_evidence_and_keeps_context_bound(monkeypatch):
    from app.rag import agentic, neighbors
    from unittest.mock import AsyncMock
    anchor=doc('original evidence')
    expand=AsyncMock(return_value=[doc('neighbor evidence')])
    monkeypatch.setattr(neighbors,'expand_neighbors',expand)
    assess=AsyncMock(return_value=agentic.Assessment(sufficient=True,missing_core=[]))
    async def retrieve(q,**kw):return {'grounded':True,'docs':[anchor],'max_score':.9}
    r=await agentic.bounded_retrieve('metric',retrieve=retrieve,assess=assess)
    assert 'neighbor evidence' in r['context'] and len(r['context'])<=6000
    assert r['agentic']['neighbor_documents']==1
    expand.reset_mock()
    async def weak(q,**kw):return {'grounded':False,'docs':[anchor],'max_score':.1}
    r=await agentic.bounded_retrieve('metric',retrieve=weak,assess=assess)
    assert not r['grounded'] and expand.await_count==0


@pytest.mark.asyncio
async def test_neighbor_cache_failure_preserves_original_assessed_evidence(monkeypatch):
    from app.rag import agentic,neighbors
    from unittest.mock import AsyncMock
    monkeypatch.setattr(neighbors,'expand_neighbors',AsyncMock(side_effect=ValueError('private path')))
    async def retrieve(q,**kw):return {'grounded':True,'docs':[doc('original')],'max_score':.9}
    r=await agentic.bounded_retrieve('metric',retrieve=retrieve,
        assess=AsyncMock(return_value=agentic.Assessment(sufficient=True,missing_core=[])))
    assert r['grounded'] and 'original' in r['context']
    assert r['agentic']['neighbor_status']=='unavailable'
    assert 'private path' not in str(r)


def test_cold_neighbor_cache_loads_once_across_threads(tmp_path,monkeypatch):
    import json,pickle,time
    from concurrent.futures import ThreadPoolExecutor
    from app.rag import neighbors
    path=tmp_path/'chunks.pkl'
    path.write_bytes(pickle.dumps([doc('anchor'),doc('adjacent')]))
    path.with_name('activation.json').write_text(json.dumps({'namespace':'build','embedding_model':'test','embedding_dimension':3}))
    original=neighbors.pickle.loads
    calls=[]
    def counted(data):
        calls.append(1)
        time.sleep(.02)
        return original(data)
    monkeypatch.setattr(neighbors.pickle,'loads',counted)
    neighbors._load.cache_clear()
    stat=path.stat()
    args=(str(path),stat.st_mtime_ns,stat.st_size,'build','test',3)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            indexes=list(pool.map(lambda _:neighbors._load_serialized(*args),range(16)))
        assert len(calls)==1 and all(index is indexes[0] for index in indexes)
    finally:
        neighbors._load.cache_clear()


def test_neighbor_manifest_mismatch_rejected_before_unpickle(tmp_path,monkeypatch):
    import json
    from app.rag import neighbors
    path=tmp_path/'chunks.pkl'
    path.write_bytes(b'not a pickle')
    path.with_name('activation.json').write_text(json.dumps({'namespace':'other'}))
    with pytest.raises(ValueError,match='identity'):
        neighbors._load(str(path),1,12,'expected','test',3)
