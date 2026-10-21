"""Read-only adjacent excerpts from the selected, trusted local chunk build.

No tokenizer model, embedding calls, remote writes or arbitrary file paths.
Neighbors are candidates for assessment, never independent proof of relevance.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import pickle
import re
from threading import RLock

from langchain_core.documents import Document


def _identity(doc: Document) -> tuple:
    meta=doc.metadata
    return (meta.get('document_sha256'),meta.get('source_file'),meta.get('page'),
            hashlib.sha256(doc.page_content.encode()).hexdigest())


def _terms(query: str) -> set[str]:
    return {word for word in re.findall(r'[\w]+',query.casefold()) if len(word)>3
            and word not in {'what','which','does','with','from','that','this','have','amount'}}


class NeighborIndex:
    def __init__(self, documents: list[Document]):
        self.documents=tuple(documents)
        self.positions={_identity(doc):i for i,doc in enumerate(documents)}

    def expand(self, anchors: list[Document], query: str, *, limit: int=2) -> list[Document]:
        if not 1<=limit<=4:
            raise ValueError('Neighbor limit must be1to4')
        originals={_identity(doc) for doc in anchors}
        candidates={}
        terms=_terms(query)
        for anchor in anchors[:4]:
            position=self.positions.get(_identity(anchor))
            if position is None or not anchor.metadata.get('document_sha256'):
                continue
            for offset in (-1,1):
                index=position+offset
                if not 0<=index<len(self.documents):
                    continue
                doc=self.documents[index]
                if (_identity(doc) in originals
                    or doc.metadata.get('document_sha256')!=anchor.metadata['document_sha256']
                    or doc.metadata.get('source_file')!=anchor.metadata.get('source_file')):
                    continue
                page,anchor_page=doc.metadata.get('page'),anchor.metadata.get('page')
                if (type(page) not in (int,float) or type(anchor_page) not in (int,float)
                    or abs(page-anchor_page)>1):
                    continue
                score=sum(term in doc.page_content.casefold() for term in terms)
                candidates.setdefault(index,(score,doc))
        out=[]
        for index,(score,doc) in sorted(candidates.items(),key=lambda item:(-item[1][0],item[0]))[:limit]:
            text=doc.page_content
            hits=[text.casefold().find(term) for term in terms if term in text.casefold()]
            # Keep a normal ingestion chunk intact, including trailing qualifiers.
            # Oversized legacy chunks still get a bounded contiguous window.
            window = 1200
            starts={max(0,min(hit-180,len(text)-window)) for hit in hits} or {0}
            start=min(starts,key=lambda offset:(-sum(term in text[offset:offset+window].casefold() for term in terms),offset))
            end=min(len(text),start+window)
            # Exact contiguous excerpt; never invent a table cell or rewrite text.
            out.append(Document(page_content=text[start:end],metadata={**doc.metadata,
                'neighbor_context':True,'neighbor_chunk_index':index,
                'original_chunk_sha256':hashlib.sha256(text.encode()).hexdigest(),
                'excerpt_start':start,'excerpt_end':end}))
        return out


@lru_cache(maxsize=1)
def _load(path: str, modified_ns: int, size: int, namespace: str, model: str, dimension: int) -> NeighborIndex:
    manifest=json.loads(Path(path).with_name('activation.json').read_text(encoding='utf-8'))
    if (manifest.get('namespace')!=namespace or manifest.get('embedding_model')!=model
        or manifest.get('embedding_dimension')!=dimension or size>16*1024*1024):
        raise ValueError('Neighbor build identity or size mismatch')
    data=Path(path).read_bytes()
    if manifest.get('chunks_sha256') and hashlib.sha256(data).hexdigest()!=manifest['chunks_sha256']:
        raise ValueError('Neighbor chunk hash mismatch')
    docs=pickle.loads(data)  # Configured release artifact only, never user input.
    if (not isinstance(docs,list) or len(docs)>10000
        or any(not isinstance(d,Document) or d.metadata.get('embedding_model')!=model
               or d.metadata.get('embedding_dimension')!=dimension for d in docs)):
        raise ValueError('Neighbor corpus belongs to a different build')
    return NeighborIndex(docs)


async def expand_neighbors(anchors: list[Document], query: str) -> list[Document]:
    from app.core.config import get_settings
    settings=get_settings()
    path=Path(settings.get_chunks_path()).resolve()
    stat=path.stat()
    index=await asyncio.to_thread(_load_serialized,str(path),stat.st_mtime_ns,stat.st_size,
                                 settings.pinecone_namespace,settings.embedding_model,settings.embedding_dimension)
    return index.expand(anchors,query)


_initialization_lock=RLock()


def _load_serialized(*args) -> NeighborIndex:
    # Cache lookup must be inside the lock: lru_cache alone permits duplicate misses.
    with _initialization_lock:
        return _load(*args)
