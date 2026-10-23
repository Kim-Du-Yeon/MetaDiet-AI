import asyncio
import copy
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.core.prompt_release_control import local_snapshot, sign_snapshot, validate_snapshot, using_snapshot, current_snapshot, ReleaseManager

def signed(release="v1"):
    key=Ed25519PrivateKey.generate()
    value=sign_snapshot(local_snapshot(release),key,report_sha256="a"*64)
    return value,key.public_key()

def test_signed_bundle_rejects_tampered_text_and_mixed_commits():
    value,key=signed()
    assert validate_snapshot(value,key).release=="v1"
    for modify in [lambda v:v["texts"].__setitem__("team.base","bypass approval"),lambda v:v["manifest"]["prompts"]["team.base"].__setitem__("commit","f"*64)]:
        broken=copy.deepcopy(value);modify(broken)
        with pytest.raises(ValueError):validate_snapshot(broken,key)

def test_unknown_variables_and_missing_registered_prompts_rejected():
    value,key=signed()
    for name in ["texts","manifest"]:
        broken=copy.deepcopy(value)
        if name=="texts":broken[name]["team.base"]+=" {private_user}"
        else:broken[name]["prompts"].pop("team.role.meal")
        with pytest.raises(ValueError):validate_snapshot(broken,key)

@pytest.mark.asyncio
async def test_context_pin_is_task_local_and_immutable_during_refresh(tmp_path):
    first=local_snapshot("v1");value,key=signed()
    async def fetch():return value
    manager=ReleaseManager(fetch=fetch,public_key=key,path=tmp_path/"good.json",initial=first,interval=0)
    async def task():
        with using_snapshot(first):
            await manager.refresh(force=True)
            await asyncio.sleep(0)
            assert current_snapshot() is first
    await asyncio.gather(task(),task())
    assert current_snapshot() is None

@pytest.mark.asyncio
async def test_last_good_survives_remote_error_and_restart(tmp_path):
    value,key=signed();path=tmp_path/"good.json"
    async def ok():return value
    manager=ReleaseManager(fetch=ok,public_key=key,path=path,initial=local_snapshot("v1"),interval=0)
    await manager.refresh(force=True)
    previous=manager.current.digest
    async def broken():raise TimeoutError("private endpoint")
    manager.fetch=broken
    assert not await manager.refresh(force=True)
    assert manager.current.digest==previous and manager.last_error=="TimeoutError"
    restored=ReleaseManager(fetch=broken,public_key=key,path=path,initial=local_snapshot("v1"),interval=0)
    assert restored.current.digest==previous
    assert "private endpoint" not in str(restored.status())


def test_plain_manifest_adapter_never_executes_runnables():
    from app.core.langsmith_prompts import plain_template
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.load import dumps
    template=ChatPromptTemplate.from_messages([("system","Hello {recent_context}")])
    assert plain_template(__import__("json").loads(dumps(template)))=="Hello {recent_context}"
    with pytest.raises(ValueError):plain_template({"id":["langchain_core","runnables","RunnableSequence"],"kwargs":{}})

def test_prompt_facade_uses_pinned_text_not_global_release():
    from app.core.prompts import get_prompt,prompt_metadata
    value,key=signed();snap=validate_snapshot(value,key)
    with using_snapshot(snap):
        assert get_prompt("team.base")==snap.text("team.base")
        assert prompt_metadata()["prompt_bundle_sha256"]==snap.digest
        assert prompt_metadata("team.base")["prompt_commit_ids"]["team.base"]


def test_runtime_reader_rejects_latest_before_network():
    from app.core.langsmith_prompts import LangSmithReleaseReader
    class NoNetwork:
        def get_prompt(self,*args):raise AssertionError("No network for unpinned latest")
    with pytest.raises(ValueError,match="latest"):
        LangSmithReleaseReader(NoNetwork()).pull("metadiet-team-base","latest")

@pytest.mark.asyncio
async def test_unchanged_release_head_does_not_refetch_eight_children():
    from app.core.langsmith_prompts import LangSmithReleaseReader
    class Client:pass
    reader=LangSmithReleaseReader(Client());calls=[]
    def pull(repo,reference):calls.append(repo);return '{}','a'*64
    reader.pull=pull
    previous={'kind':'signed','origin_commit':'a'*64}
    assert await reader.fetch(previous=previous)==previous
    assert len(calls)==1
