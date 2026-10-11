import json
import pytest


def test_cached_result_cannot_cross_ranking_configuration(tmp_path):
    from scripts.eval.run_frozen_rerank import cached_row
    path = tmp_path / "cached.json"
    path.write_text(json.dumps({"cache_signature": "old-model"}), encoding="utf8")
    with pytest.raises(ValueError, match="configuration"):
        cached_row(path, "new-model")


def test_diagnostic_cannot_score_changed_gold_with_frozen_dataset_hash(tmp_path):
    from scripts.eval.run_frozen_rerank import validate_frozen_dataset
    dataset = tmp_path / "gold.json"
    dataset.write_text("[]", encoding="utf8")
    with pytest.raises(ValueError, match="dataset"):
        validate_frozen_dataset({"dataset_sha256": "wrong", "cases": []}, dataset)
