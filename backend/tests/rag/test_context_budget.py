from langchain_core.documents import Document
from app.rag.retriever import format_docs


def test_fourth_retrieved_document_is_available_to_answer():
    docs = [Document(page_content=f"evidence-{i}", metadata={"source_file": "a.pdf", "page": i}) for i in range(1, 5)]
    assert "evidence-4" in format_docs(docs)


def test_context_budget_includes_citation_markers():
    docs = [Document(page_content="x" * 3000, metadata={"source_file": "a.pdf", "page": i}) for i in range(1, 5)]
    context = format_docs(docs, max_chars=6000)
    assert len(context) <= 6000
    assert "[출처: a.pdf, 페이지: 1]" in context
