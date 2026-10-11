"""Analyze candidate misses vs ordering losses, with fact-group bootstrap intervals."""
import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


def interval(differences):
    rng = random.Random(20261009)
    groups = list(differences)
    draws = sorted(sum(rng.choice(groups) for _ in groups) / len(groups) for _ in range(2000))
    return {"mean_difference": sum(groups) / len(groups), "ci95": [draws[49], draws[1949]],
            "unit": "fact group, paired bootstrap, 2000 draws"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    path = args.directory / "report.json"
    report = json.loads(path.read_text(encoding="utf8"))
    rows = report["cases"]
    baseline = {row["id"]: row for row in rows if row["variant"] == "none" and row["status"] == "completed"}
    out = {"report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "scope": "development retrieval diagnostics; literal excerpts are not answer accuracy",
        "grounding_policy": "Answer experiment uses all frozen contexts to isolate ranking; production score thresholds not evaluated",
        "language_note": "KO refers to original user questions. Rerank queries use the same frozen English translations.",
        "variants": {}}
    for variant in ("none", "minilm", "multibert", "jev"):
        subset = [row for row in rows if row["variant"] == variant and row["status"] == "completed"]
        errors = Counter()
        language = {}
        for row in subset:
            category = ("candidate_page_missing" if not row["candidate_page_hit"] else
                        "reranking_lost_page" if not row["page_hit"] else
                        "page_hit_but_literal_excerpt_missing" if not row["excerpt_hit"] else "page_and_excerpt_hit")
            errors[category] += 1
        for lang in ("en", "ko"):
            selected = [row for row in subset if row["language"] == lang]
            language[lang] = {"n": len(selected), **{metric: sum(row[metric] for row in selected) / len(selected)
                for metric in ("page_hit", "excerpt_hit", "mrr", "seconds")}} if selected else {"n": 0}
        groups = defaultdict(list)
        for row in subset:
            if row["id"] in baseline:
                groups[row["case_group"]].append(float(row["excerpt_hit"]) - float(baseline[row["id"]]["excerpt_hit"]))
        differences = [sum(values) / len(values) for values in groups.values()]
        out["variants"][variant] = {"error_categories": dict(errors), "languages": language,
            "excerpt_difference_vs_none": interval(differences) if differences else None,
            "jev_model_calls": sum(len(row.get("events", [])) for row in subset),
            "usage": dict(sum((Counter(event.get("usage", {})) for row in subset for event in row.get("events", [])), Counter()))}
    (args.directory / "diagnostics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
