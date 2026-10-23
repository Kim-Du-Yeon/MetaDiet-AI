import importlib.util
import hashlib
from pathlib import Path
import pytest

def test_saved_comparison_import_rejects_changed_artifacts(tmp_path):
    path=Path(__file__).resolve().parents[2]/'scripts/eval/publish_prompt_comparison.py'
    spec=importlib.util.spec_from_file_location('publish_saved_prompts',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    artifact=tmp_path/'paired.json';artifact.write_text('{}')
    summary={'source_hashes':{'paired.json':hashlib.sha256(artifact.read_bytes()).hexdigest()}}
    module.verify_sources(tmp_path,summary)
    artifact.write_text('{"tampered":true}')
    with pytest.raises(ValueError):module.verify_sources(tmp_path,summary)
