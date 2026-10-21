"""Request boundary and background refresh; no remote work on import."""
import asyncio
from functools import lru_cache
import json
from pathlib import Path
from app.core.config import get_settings
from app.core.prompt_release_control import ReleaseManager, local_snapshot, using_snapshot

def approval_key():
    value=get_settings().prompt_approval_public_key
    if not value:
        path=Path(__file__).resolve().parents[1]/"prompts"/"approval-public-key.json"
        if path.is_file():value=json.loads(path.read_text(encoding="utf-8"))["public_key"]
    return value or None

@lru_cache(maxsize=1)
def get_release_manager():
    settings=get_settings()
    async def fetch():
        from app.core.langsmith_prompts import make_client,LangSmithReleaseReader
        client=make_client()
        try:return await LangSmithReleaseReader(client,settings.prompt_remote_channel).fetch(previous=manager.current.wire)
        finally:client.close()
    manager=ReleaseManager(fetch=fetch,public_key=approval_key(),path=Path(settings.prompt_last_good_path),
        initial=local_snapshot(settings.prompt_release),interval=max(10,settings.prompt_refresh_seconds),load_persisted=settings.prompt_remote_enabled)
    return manager

async def refresh_loop():
    while True:
        if get_settings().prompt_remote_enabled:await get_release_manager().refresh()
        await asyncio.sleep(1)

def experiment_policy():
    s=get_settings()
    if not s.prompt_ab_enabled or not s.prompt_ab_live_approved:return None
    from app.core.prompt_assignment import ExperimentPolicy
    from app.core.prompt_release_control import validate_snapshot
    value=json.loads(Path(s.prompt_ab_manifest_path).read_text(encoding="utf-8"))
    return ExperimentPolicy(s.prompt_ab_experiment_id,s.prompt_ab_salt.encode(),
        tuple(validate_snapshot(v,approval_key()) for v in value["variants"]),enabled=True,approved=True,
        percent_b=value.get("percent_b",50),unit=value.get("unit","user"))

async def invoke_with_prompt_pin(graph,graph_input,config):
    from app.core.prompt_assignment import choose_snapshot
    manager=get_release_manager();saved=None
    policy=experiment_policy()
    if graph_input is None or policy is not None:
        state=await graph.aget_state(config)
        values=getattr(state,"values",{}) if state is not None else {}
        if isinstance(values,dict):saved=values.get("prompt_pin")
    snapshot=choose_snapshot(manager.current,saved,pending=graph_input is None,policy=policy,
        user=(graph_input or {}).get("user_id",""),thread=config.get("configurable",{}).get("thread_id",""),trusted_key=approval_key())
    if graph_input is not None:graph_input={**graph_input,"prompt_pin":snapshot.wire}
    elif saved is None:await graph.aupdate_state(config,{"prompt_pin":snapshot.wire})
    invocation={**config,"metadata":{**config.get("metadata",{}),**snapshot.metadata()}}
    with using_snapshot(snapshot):return await graph.ainvoke(graph_input,config=invocation)
