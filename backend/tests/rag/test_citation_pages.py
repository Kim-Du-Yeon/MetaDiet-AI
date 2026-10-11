from scripts.build_rag import citation_metadata


def test_citations_are_one_based_without_losing_loader_index():
    source = {"page": 23, "page_label": "20"}
    result = citation_metadata(source)
    assert result["page"] == result["pdf_page"] == 24
    assert result["pdf_page_index"] == 23
    assert result["page_label"] == "20"
    assert source["page"] == 23
