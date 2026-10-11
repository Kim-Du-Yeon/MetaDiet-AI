"""Source-reviewed anchors and table-cell diagnostics, not clinical approval."""
import argparse
import json
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.eval.run_full_recipe_comparison import ROOT, eligible_recipes, dump, normalized, sha


def table_rows(block):
    if "cells" in block:
        return block["cells"]
    cells = block.get("data", {}).get("table_cells", [])
    rows = {}
    for cell in cells:
        row = cell["start_row_offset_idx"]
        col = cell["start_col_offset_idx"]
        rows.setdefault(row, {})[col] = cell.get("text", "")
    return [[cols.get(c, "") for c in range(max(cols) + 1)] for _, cols in sorted(rows.items())]


def row_preserved(blocks, anchor):
    for block in blocks:
        if block["kind"] != "table":
            continue
        for row in table_rows(block):
            if not any(normalized(anchor["row_label"]) in normalized(cell or "") for cell in row):
                continue
            if all(int(col) < len(row) and re.fullmatch(re.escape(normalized(value)) + r"(?:\([^)]*\))?", normalized(row[int(col)] or ""))
                   for col, value in anchor["expected_cells"].items()):
                return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--anchors", type=Path, default=ROOT.parent / "docs/rag_experiments/parser_preservation_v1.json")
    parser.add_argument("--dataset", type=Path, default=ROOT.parent / "docs/rag_experiments/gold_core40_v2.json")
    args = parser.parse_args()
    anchors = json.loads(args.anchors.read_text(encoding="utf8"))
    cases = json.loads(args.dataset.read_text(encoding="utf8"))
    report = {"anchors_sha256": sha(args.anchors), "dataset_sha256": sha(args.dataset), "review_scope": anchors["review_scope"], "recipes": []}
    for name, strategy in eligible_recipes(args.directory, include_controls=False):
        blocks_by_source = {p.name.removesuffix(".json"): json.loads(p.read_text(encoding="utf8"))["blocks"]
                            for p in (args.directory / "blocks" / name).glob("*.json")}
        def page_blocks(source, pages):
            return [b for b in blocks_by_source[source] if b["pdf_page"] in pages]
        rows = []
        for anchor in anchors["text_anchors"]:
            text = normalized("\n".join(b["text"] for b in page_blocks(anchor["source"], [anchor["page"]])))
            missing = [t for t in anchor["terms"] if normalized(t) not in text]
            rows.append({"id": anchor["id"], "type": "text_anchor", "passed": not missing, "missing": missing})
        for anchor in anchors["table_rows"]:
            rows.append({"id": anchor["id"], "type": "table_row", "passed": row_preserved(page_blocks(anchor["source"], [anchor["page"]]), anchor)})
        seen = set()
        for case in cases:
            group = case.get("case_group", case["id"])
            if group in seen:
                continue
            seen.add(group)
            evidence = case.get("acceptable_evidence") or [{"source": case["gold_source"], "pdf_pages": [case["gold_page"]]}]
            passed = any(normalized(case["gold_excerpt"]) in normalized("\n".join(b["text"] for b in page_blocks(e["source"], e["pdf_pages"]))) for e in evidence)
            rows.append({"id": group, "type": "gold_excerpt_preserved", "passed": passed})
        report["recipes"].append({"recipe": f"{name}-{strategy}", "checks": rows,
            "totals": {kind: {"passed": sum(r["passed"] for r in rows if r["type"] == kind), "n": sum(r["type"] == kind for r in rows)}
                       for kind in ("text_anchor", "table_row", "gold_excerpt_preserved")}})
    dump(args.directory / "preservation-report.json", report)
    print(json.dumps([{k: v for k, v in r.items() if k != "checks"} for r in report["recipes"]], ensure_ascii=False))


if __name__ == "__main__":
    main()
