import json
import pytest
from pathlib import Path
from scripts.eval.cache_artifacts import save_json

def test_atomic_snapshot_retries_only_transient_replace(monkeypatch,tmp_path):
    original=Path.replace;calls=[]
    def replace(path,target):
        calls.append(1)
        if len(calls)<3:raise PermissionError('sharing violation')
        return original(path,target)
    monkeypatch.setattr(Path,'replace',replace)
    monkeypatch.setattr('scripts.eval.cache_artifacts.time.sleep',lambda _:None)
    target=tmp_path/'paired.json'
    save_json(target,{'completed':1})
    assert json.loads(target.read_text())=={'completed':1} and len(calls)==3

def test_atomic_snapshot_retains_temp_and_bounds_permanent_failure(monkeypatch,tmp_path):
    calls=[]
    def replace(*args):calls.append(1);raise PermissionError()
    monkeypatch.setattr(Path,'replace',replace)
    monkeypatch.setattr('scripts.eval.cache_artifacts.time.sleep',lambda _:None)
    target=tmp_path/'paired.json'
    with pytest.raises(PermissionError):save_json(target,{'completed':1})
    assert len(calls)==6 and target.with_suffix('.tmp').exists()
