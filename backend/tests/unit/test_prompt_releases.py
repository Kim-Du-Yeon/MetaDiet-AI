import hashlib
import json
from types import SimpleNamespace

import pytest

from app.core import prompts


def test_baseline_prompt_identity_and_metadata_have_no_user_content():
    text = prompts.get_prompt('team.base')
    assert '실제 저장은 확인 버튼 뒤에만 가능합니다.' in text
    metadata = prompts.prompt_metadata('team.base')
    assert metadata['prompt_release']=='v1'
    assert metadata['prompt_sha256']==hashlib.sha256(text.encode()).hexdigest()
    assert metadata['prompt_version']=='1.0.0'
    assert 'template' not in metadata and 'text' not in metadata
    assert metadata['prompt_bundle_sha256']=='4c40f46e4c2aa01b5ba7c78f456cff11b11907a4730e697288f796694ec7a741'


@pytest.mark.parametrize('release',['../v1','/tmp/v1','unknown','v999'])
def test_unknown_or_path_release_is_rejected(release):
    with pytest.raises(ValueError): prompts.get_prompt('team.base',release=release)


def test_corrupt_prompt_cannot_be_silently_loaded(tmp_path,monkeypatch):
    root = tmp_path/'releases'
    root.mkdir()
    data = {'release':'v2','prompts':{'team.base':{
        'version':'1.0.0','text':'Changed but old digest','sha256':'0'*64}}}
    (root/'v2.json').write_text(json.dumps(data))
    monkeypatch.setattr(prompts,'RELEASE_ROOT',root)
    prompts.load_release.cache_clear()
    try:
        with pytest.raises(ValueError,match='hash'): prompts.get_prompt('team.base',release='v2')
    finally:
        prompts.load_release.cache_clear()


async def test_runtime_trace_tracks_system_prompt_without_user_text():
    from langchain_core.messages import AIMessage
    from app.agents.runtime import run_agent,ExecutionBudget
    seen=[]
    class Model:
        async def ainvoke(self,messages,config=None):
            seen.append(config)
            return AIMessage(content='완료')
    await run_agent(model=Model(),instruction='Static synthetic instruction',
        request='private synthetic input must not enter metadata',tools=[],budget=ExecutionBudget())
    meta=seen[0]['metadata']
    assert meta['prompt_release']=='v1'
    assert meta['system_instruction_sha256']==hashlib.sha256(b'Static synthetic instruction').hexdigest()
    assert 'private synthetic' not in json.dumps(meta)


def test_valid_new_release_selection_and_immutable_cached_entries(tmp_path,monkeypatch):
    text='A different synthetic instruction'
    data={'release':'v2','prompts':{'team.base':{'version':'2.0.0','text':text,
        'sha256':hashlib.sha256(text.encode()).hexdigest()}}}
    (tmp_path/'v2.json').write_text(json.dumps(data))
    monkeypatch.setattr(prompts,'RELEASE_ROOT',tmp_path)
    monkeypatch.setattr(prompts,'get_settings',lambda:SimpleNamespace(prompt_release='v2'))
    prompts.load_release.cache_clear()
    try:
        assert prompts.get_prompt('team.base')==text
        assert prompts.prompt_metadata('team.base')['prompt_version']=='2.0.0'
        with pytest.raises(TypeError): prompts.load_release('v2')[0]['team.base']['text']='mutated'
    finally:
        prompts.load_release.cache_clear()
