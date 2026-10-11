from langchain_core.documents import Document
from app.rag.retriever import _rrf


def test_pinecone_float_page_and_bm25_integer_page_are_same_chunk():
    dense = Document(page_content="identical evidence", metadata={"source_file": "a.pdf", "page": 11.0})
    sparse = Document(page_content="identical evidence", metadata={"source_file": "a.pdf", "page": 11})
    assert len(_rrf([dense], [sparse])) == 1


def test_chunks_with_same_prefix_but_different_evidence_are_not_collapsed():
    prefix = "x" * 60
    docs = [Document(page_content=prefix + text, metadata={"source_file": "a.pdf", "page": 11}) for text in ("fact A", "fact B")]
    assert len(_rrf(docs, [])) == 2
