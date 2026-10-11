import math
from langchain_core.documents import Document
from scripts.eval.run_retrieval_ablation import ranking_metrics


def test_page_metrics_deduplicate_same_page_and_require_matching_source():
    documents = [Document(page_content="", metadata={"source_file": source, "page": page})
                 for source, page in (("wrong.pdf", 24), ("wrong.pdf", 24), ("gold.pdf", 24.0))]
    scores = ranking_metrics(documents, {"gold_source": "gold.pdf", "gold_page": 24})
    assert scores["page_hit"] and scores["source_hit"]
    assert scores["mrr"] == .5
    assert scores["ndcg"] == 1 / math.log2(3)


def test_missing_page_is_not_a_hit():
    scores = ranking_metrics([], {"gold_source": "gold.pdf", "gold_page": 24})
    assert scores == {"source_hit": False, "page_hit": False, "mrr": 0, "ndcg": 0}
