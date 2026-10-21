"""Private, data-only LangSmith prompt transport. Never deserialize a Runnable."""
import asyncio
import json
import re
from app.core.prompt_release_control import REPOS

RELEASE_REPO="metadiet-release-manifest"

def plain_template(manifest):
    if not isinstance(manifest,dict):raise ValueError("Invalid serialized template")
    kind=(manifest.get("id") or [None])[-1];kwargs=manifest.get("kwargs",{})
    if kind=="ChatPromptTemplate":
        messages=kwargs.get("messages",[])
        if len(messages)!=1:raise ValueError("Exactly one system template required")
        return plain_template(messages[0])
    if kind=="SystemMessage":
        if not isinstance(kwargs.get("content"),str):raise ValueError("Text-only template required")
        return kwargs["content"]
    if kind=="SystemMessagePromptTemplate":return plain_template(kwargs.get("prompt"))
    if kind=="PromptTemplate" and kwargs.get("template_format","f-string")=="f-string" and isinstance(kwargs.get("template"),str):return kwargs["template"]
    raise ValueError("Remote runnable/model/schema is forbidden")

def make_client(*,timeout_ms=2000):
    from langsmith import Client
    from urllib3.util.retry import Retry
    from app.core.config import get_settings
    s=get_settings()
    if not s.langsmith_api_key:raise ValueError("LangSmith key not configured")
    return Client(api_url=s.langsmith_endpoint,api_key=s.langsmith_api_key,timeout_ms=timeout_ms,
                  retry_config=Retry(total=0),auto_batch_tracing=False,hide_inputs=True,hide_outputs=True,
                  disable_prompt_cache=True)

class LangSmithReleaseReader:
    def __init__(self,client,channel="production"):
        if channel not in {"production","staging"}:raise ValueError("Invalid release channel")
        self.client=client;self.channel=channel
    def pull(self,repo,reference,*,allow_latest=False):
        if reference=="latest" and not allow_latest:raise ValueError("Mutable latest is forbidden at runtime")
        if repo not in {*REPOS.values(),RELEASE_REPO}:raise ValueError("Unknown private prompt repo")
        record=self.client.get_prompt(repo)
        if record is None or record.is_public is not False:raise ValueError("Private prompt required")
        commit=self.client.pull_prompt_commit(repo+":"+reference,include_model=False,skip_cache=True)
        if not re.fullmatch(r"[a-f0-9]{64}",commit.commit_hash):raise ValueError("Full prompt commit ID required")
        if reference not in {"production","staging","latest"} and commit.commit_hash!=reference:raise ValueError("Commit mismatch")
        return plain_template(commit.manifest),commit.commit_hash
    async def fetch(self,previous=None):
        text,commit=await asyncio.to_thread(self.pull,RELEASE_REPO,self.channel)
        if previous and previous.get("kind")=="signed" and previous.get("origin_commit")==commit:
            return previous
        if len(text.encode())>32000:raise ValueError("Oversized remote manifest")
        value=json.loads(text)
        if set(value)!={"kind","manifest","signature"}:raise ValueError("Release manifest contains unexpected fields")
        entries=value["manifest"]["prompts"]
        if set(entries)!=set(REPOS):raise ValueError("Incomplete release")
        for n,e in entries.items():
            if e.get("repo")!=REPOS[n] or not re.fullmatch(r"[a-f0-9]{64}",e.get("commit","")):raise ValueError("Invalid prompt reference")
        values=await asyncio.gather(*(asyncio.to_thread(self.pull,e["repo"],e["commit"]) for e in entries.values()))
        value["texts"]={name:result[0] for name,result in zip(entries,values)}
        value["origin_commit"]=commit
        return value
