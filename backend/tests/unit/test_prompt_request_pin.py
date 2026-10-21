from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.core.prompt_release_control import local_snapshot,current_snapshot,using_snapshot
from app.core.prompt_service import invoke_with_prompt_pin

@pytest.mark.asyncio
async def test_request_and_resumed_confirmation_keep_one_snapshot(monkeypatch):
    from app.core import prompt_service
    first=local_snapshot();manager=SimpleNamespace(current=first)
    monkeypatch.setattr(prompt_service,"get_release_manager",lambda:manager)
    monkeypatch.setattr(prompt_service,"experiment_policy",lambda:None)
    monkeypatch.setattr(prompt_service,"approval_key",lambda:None)
    seen=[]
    class Graph:
        values={}
        async def aget_state(self,config):return SimpleNamespace(values=self.values)
        async def aupdate_state(self,config,value):self.values.update(value)
        async def ainvoke(self,value,config):
            if value:self.values.update(value)
            seen.append((current_snapshot().serialized,config["metadata"]["prompt_bundle_sha256"]))
            return self.values
    graph=Graph();config={"configurable":{"thread_id":"synthetic-thread"}}
    await invoke_with_prompt_pin(graph,{"user_id":"synthetic-owner"},config)
    assert graph.values["prompt_pin"]==first.wire
    # Simulate independently refreshed manager while pending flow is resumed.
    manager.current=SimpleNamespace(wire={"not":"used"})
    await invoke_with_prompt_pin(graph,None,config)
    assert seen[0]==seen[1] and current_snapshot() is None

@pytest.mark.asyncio
async def test_reused_model_metadata_is_resolved_at_each_call(monkeypatch):
    from app.core.llm import get_chat_model
    from langchain_core.messages import AIMessage
    from app.core import prompts
    model=get_chat_model();seen=[]
    class Provider:
        async def ainvoke(self,input,config=None,**kwargs):
            seen.append(config["metadata"]);return AIMessage(content="ok")
    model._provider=Provider()
    with using_snapshot(local_snapshot()):await model.ainvoke("synthetic")
    await model.ainvoke("synthetic")
    assert seen[0]["prompt_bundle_sha256"]!=seen[1]["prompt_bundle_sha256"]
    assert seen[1]["prompt_bundle_sha256"]==prompts.prompt_metadata()["prompt_bundle_sha256"]
