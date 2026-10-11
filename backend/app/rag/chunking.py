"""Three offline chunk recipes; parent expansion never changes evidence provenance."""
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class ChunkConfig:
    strategy: Literal["page", "parent_child", "section"] = "page"
    parent_chars: int = 1800
    child_chars: int = 400
    section_chars: int = 1200
    overlap: int = 50

    def __post_init__(self):
        if self.strategy not in {"page", "parent_child", "section"}:
            raise ValueError("Unknown chunk strategy")
        if min(self.parent_chars, self.child_chars, self.section_chars) <= 0:
            raise ValueError("Chunk sizes must be positive")
        if not 0 <= self.overlap < min(self.child_chars, self.parent_chars, self.section_chars):
            raise ValueError("Overlap must be smaller than chunk sizes")


def _windows(text, size, overlap):
    start = 0
    while start < len(text):
        yield text[start:start + size]
        if start + size >= len(text):
            break
        start += size - overlap


def chunk_blocks(blocks: list[dict], metadata: dict, config: ChunkConfig) -> dict:
    recipe = asdict(config)
    recipe_id = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:16]
    usable = [b for b in blocks if b.get("text", "").strip() and b.get("pdf_page") is not None
              and b.get("kind") != "image" and not b.get("derived", False)]
    chunks, parents = [], {}

    def unit(text, group, index, suffix):
        citation_blocks = [{key: block.get(key) for key in ("id", "kind", "pdf_page", "pdf_page_label", "printed_page", "provenance")} for block in group]
        page_numbers = {b["pdf_page"] for b in group}
        page_numbers.update(prov["page_no"] for b in group for prov in b.get("provenance", []) if prov.get("page_no") is not None)
        meta = {**metadata, "recipe_id": recipe_id, "strategy": config.strategy,
                "pdf_pages": sorted(page_numbers), "block_ids": [b["id"] for b in group], "evidence_blocks": citation_blocks,
                "heading": next((b["text"] for b in group if b["kind"] == "heading"), None)}
        identifier = hashlib.sha256((str(metadata.get("sha256")) + recipe_id + suffix + str(index)
            + json.dumps(meta, sort_keys=True) + text).encode()).hexdigest()
        return {"id": identifier, "text": text, "metadata": meta}

    groups = []
    if config.strategy in {"page", "parent_child"}:
        pages = {}
        for block in usable:
            pages.setdefault(block["pdf_page"], []).append(block)
        groups = list(pages.values())
    else:
        current = []
        for block in usable:
            if block["kind"] == "heading" and current:
                groups.append(current)
                current = []
            current.append(block)
        if current:
            groups.append(current)

    for group_index, group in enumerate(groups):
        text = "\n\n".join(b["text"] for b in group)
        if config.strategy == "page":
            chunks.append(unit(text, group, group_index, "page"))
        elif config.strategy == "parent_child":
            for parent_index, parent_text in enumerate(_windows(text, config.parent_chars, config.overlap)):
                parent = unit(parent_text, group, parent_index, f"parent:{group_index}")
                parents[parent["id"]] = parent
                for child_index, child_text in enumerate(_windows(parent_text, config.child_chars, config.overlap)):
                    child = unit(child_text, group, child_index, parent["id"])
                    child["parent_id"] = parent["id"]
                    chunks.append(child)
        else:
            # Pack whole structural blocks, keeping table cells together. Oversized
            # prose is capped; oversized tables stay intact and are explicitly marked.
            packed, packed_blocks = [], []
            def flush():
                if packed:
                    chunks.append(unit("\n\n".join(packed), packed_blocks, len(chunks), "section"))
                    packed.clear()
                    packed_blocks.clear()
            heading = ""
            for block in group:
                if block["kind"] == "heading":
                    heading = block["text"]
                parts = [block["text"]] if block["kind"] == "table" else list(_windows(block["text"], config.section_chars, config.overlap))
                for part in parts:
                    if packed and len("\n\n".join(packed + [part])) > config.section_chars:
                        flush()
                    packed.append(part)
                    packed_blocks.append(block)
            flush()
            for chunk in chunks:
                if chunk["metadata"]["heading"] is None and chunk["metadata"]["block_ids"] and heading:
                    # Heading is metadata, not an invented source passage.
                    if chunk["metadata"]["block_ids"][0] in {b["id"] for b in group}:
                        chunk["metadata"]["heading"] = heading
    return {"recipe": recipe, "recipe_id": recipe_id, "search_chunks": chunks, "parents": parents}


def expand_context(bundle: dict, chunk_ids: list[str]) -> list[dict]:
    by_id = {chunk["id"]: chunk for chunk in bundle["search_chunks"]}
    result, seen = [], set()
    for identifier in chunk_ids:
        child = by_id[identifier]
        context = bundle["parents"][child["parent_id"]] if child.get("parent_id") else child
        if context["id"] not in seen:
            result.append(context)
            seen.add(context["id"])
    return result
