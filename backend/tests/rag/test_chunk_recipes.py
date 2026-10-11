import pytest


def test_parent_child_searches_small_units_but_returns_complete_parent():
    from app.rag.chunking import ChunkConfig, chunk_blocks, expand_context
    blocks = [{"id": "b1", "kind": "text", "pdf_page": 7, "text": "abcdefghij" * 30, "derived": False}]
    config = ChunkConfig(strategy="parent_child", parent_chars=180, child_chars=60, overlap=10)
    bundle = chunk_blocks(blocks, {"sha256": "a" * 64, "source_file": "a.pdf"}, config)
    assert max(len(c["text"]) for c in bundle["search_chunks"]) <= 60
    first = bundle["search_chunks"][0]
    expanded = expand_context(bundle, [first["id"], bundle["search_chunks"][1]["id"]])
    assert len(expanded) == 1
    assert len(expanded[0]["text"]) == 180
    assert expanded[0]["metadata"]["pdf_pages"] == [7]


def test_page_chunks_keep_page_boundary_and_unreviewed_images_out():
    from app.rag.chunking import ChunkConfig, chunk_blocks
    blocks = [{"id": "one", "kind": "text", "pdf_page": 1, "text": "first"},
              {"id": "two", "kind": "text", "pdf_page": 2, "text": "second"},
              {"id": "image", "kind": "image", "pdf_page": 1, "text": "invented caption", "derived": True}]
    result = chunk_blocks(blocks, {"sha256": "b", "source_file": "b.pdf"}, ChunkConfig(strategy="page"))
    assert [c["text"] for c in result["search_chunks"]] == ["first", "second"]
    assert [c["metadata"]["pdf_pages"] for c in result["search_chunks"]] == [[1], [2]]


def test_sections_preserve_headings_tables_and_stable_recipe_ids():
    from app.rag.chunking import ChunkConfig, chunk_blocks
    blocks = [{"id": "h1", "kind": "heading", "pdf_page": 2, "text": "Protein"},
              {"id": "t1", "kind": "table", "pdf_page": 2, "text": "adult | 10-20%", "cells": [["adult", "10-20%"]]},
              {"id": "h2", "kind": "heading", "pdf_page": 3, "text": "Fat"},
              {"id": "b2", "kind": "text", "pdf_page": 3, "text": "15-30%"}]
    meta = {"sha256": "c", "source_file": "c.pdf"}
    result = chunk_blocks(blocks, meta, ChunkConfig(strategy="section"))
    assert len(result["search_chunks"]) == 2
    assert "adult | 10-20%" in result["search_chunks"][0]["text"]
    assert result == chunk_blocks(blocks, meta, ChunkConfig(strategy="section"))
    assert result["search_chunks"][0]["id"] != chunk_blocks(blocks, meta, ChunkConfig(strategy="page"))["search_chunks"][0]["id"]


def test_invalid_overlap_rejected():
    from app.rag.chunking import ChunkConfig
    with pytest.raises(ValueError):
        ChunkConfig(strategy="parent_child", child_chars=50, overlap=50)


def test_multpage_table_keeps_complete_citation_metadata():
    from app.rag.chunking import ChunkConfig, chunk_blocks
    block = {"id": "table", "kind": "table", "text": "Header | Value", "pdf_page": 10,
             "pdf_page_label": "vi", "printed_page": "6", "provenance": [{"page_no": 10}, {"page_no": 11}]}
    chunk = chunk_blocks([block], {"sha256": "d"}, ChunkConfig(strategy="section"))["search_chunks"][0]
    assert chunk["metadata"]["pdf_pages"] == [10, 11]
    citation = chunk["metadata"]["evidence_blocks"][0]
    assert citation["pdf_page_label"] == "vi"
    assert citation["printed_page"] == "6"
    assert citation["provenance"] == block["provenance"]
