from langchain_core.documents import Document
from scripts.eval.run_retrieval_ablation import ranking_metrics


def test_equivalent_pages_are_relevant_and_ndcg_uses_all_relevant_ranks():
    docs = [Document(page_content="", metadata={"source_file": "who.pdf", "page": p}) for p in (12, 24)]
    case = {"gold_source": "who.pdf", "gold_page": 24,
            "acceptable_evidence": [{"source": "who.pdf", "pdf_pages": [12, 24]}]}
    result = ranking_metrics(docs, case)
    assert result["mrr"] == 1
    assert result["ndcg"] == 1


def test_same_number_in_another_document_is_not_relevant():
    docs = [Document(page_content="", metadata={"source_file": "wrong.pdf", "page": 12})]
    case = {"gold_source": "who.pdf", "gold_page": 24,
            "acceptable_evidence": [{"source": "who.pdf", "pdf_pages": [12, 24]}]}
    assert not ranking_metrics(docs, case)["page_hit"]
