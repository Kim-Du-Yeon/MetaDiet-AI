"""Atomic signed template releases. No provider/network I/O on import."""
from __future__ import annotations
import asyncio
import base64
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Awaitable, Callable
from langchain_core.prompts.string import get_template_variables

CONTRACTS={"team.base":(),"team.role.meal":(),"team.role.goal":(),"team.role.evidence":(),
 "team.compact_followup":(),"legacy.intent_classification":("pending_info","recent_context"),
 "legacy.food_extraction":("logged_meals","recent_context"),"rag.query_translation":()}
OUTPUTS={name:("intent_enum_v1" if name=="legacy.intent_classification" else "food_json_v1" if name=="legacy.food_extraction" else "english_query_v1" if name=="rag.query_translation" else "tool_coaching_v1") for name in CONTRACTS}
REPOS={name:"metadiet-"+name.replace(".","-").replace("_","-") for name in CONTRACTS}
_CONTEXT:ContextVar[Snapshot|None]=ContextVar("prompt_release_snapshot",default=None)
_SENSITIVE=re.compile(r"(?:AIza[\w-]{20,}|lsv2_[\w-]{16,}|sk-[\w-]{16,}|[\w.+-]+@[\w.-]+\.[a-z]{2,}|Bearer\s+[\w.-]{16,})",re.I)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def validate_texts(manifest,texts):
    if set(manifest.get("prompts",{}))!=set(CONTRACTS) or set(texts)!=set(CONTRACTS):raise ValueError("Expected complete eight-prompt bundle")
    for name,variables in CONTRACTS.items():
        entry=manifest["prompts"][name];text=texts[name]
        if not isinstance(text,str) or not 1<=len(text.encode())<=16000 or _SENSITIVE.search(text):raise ValueError("Invalid static template")
        if entry.get("repo")!=REPOS[name] or not re.fullmatch(r"[a-f0-9]{64}",entry.get("commit","")):raise ValueError("Invalid immutable prompt reference")
        if entry.get("sha256")!=hashlib.sha256(text.encode()).hexdigest():raise ValueError("Prompt hash mismatch")
        if tuple(sorted(get_template_variables(text,"f-string")))!=variables or entry.get("input_variables")!=list(variables):raise ValueError("Prompt variable contract mismatch")
        if entry.get("output_contract")!=OUTPUTS[name] or not re.fullmatch(r"\d+\.\d+\.\d+",entry.get("version","")):raise ValueError("Code-owned output contract mismatch")

@dataclass(frozen=True)
class Snapshot:
    serialized:str
    digest:str
    release:str
    @property
    def wire(self):return json.loads(self.serialized)
    def text(self,name):return self.wire["texts"][name]
    def metadata(self):
        value=self.wire;m=value["manifest"]
        return {"prompt_release":self.release,"prompt_bundle_sha256":self.digest,
          "prompt_scope":"registered_primary_templates",
          "prompt_commit_ids":{n:e["commit"] if value["kind"]!="local" else None for n,e in m["prompts"].items()},
          "prompt_source":value["kind"],
          "prompt_hashes":{n:e["sha256"] for n,e in m["prompts"].items()},
          "prompt_release_commit":value.get("origin_commit"),
          **value.get("experiment",{})}

def _snapshot(value):
    if len(canonical(value))>64000:raise ValueError("Prompt bundle too large")
    manifest=value["manifest"]
    if manifest.get("schema_version")!=1 or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}",manifest.get("release","")):raise ValueError("Invalid release manifest")
    validate_texts(manifest,value["texts"])
    return Snapshot(canonical(value).decode(),digest(manifest),manifest["release"])

def local_snapshot(release="v1"):
    from app.core.prompts import load_release
    entries,_=load_release(release)
    prompts={n:{"repo":REPOS[n],"commit":e["sha256"],"sha256":e["sha256"],"version":e["version"],
                 "input_variables":list(CONTRACTS[n]),"output_contract":OUTPUTS[n]} for n,e in entries.items()}
    return _snapshot({"kind":"local","manifest":{"schema_version":1,"release":release,"prompts":prompts},
                      "texts":{n:e["text"] for n,e in entries.items()},"origin_commit":None})

def sign_snapshot(snapshot,private_key,*,report_sha256):
    value=snapshot.wire if isinstance(snapshot,Snapshot) else json.loads(json.dumps(snapshot))
    if not re.fullmatch(r"[a-f0-9]{64}",report_sha256):raise ValueError("Validation report SHA required")
    value["kind"]="signed"
    value["manifest"]["validation"]={"passed":True,"criteria":"prompt-control-v1","report_sha256":report_sha256}
    _snapshot(value)
    value["signature"]=base64.b64encode(private_key.sign(canonical(value["manifest"]))).decode()
    return value

def public_key(value):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(value,validate=True)) if isinstance(value,str) else value

def validate_snapshot(value,trusted_key=None):
    try:
        if not isinstance(value,dict):raise ValueError("Invalid snapshot")
        experiment=value.get("experiment",{})
        if set(experiment)-{"prompt_experiment_id","prompt_experiment_group","prompt_experiment_config_sha256"} or any(not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}",str(x)) for x in experiment.values()):raise ValueError("Invalid experiment metadata")
        if value.get("kind")=="local":
            expected=local_snapshot(value["manifest"]["release"])
            if {k:v for k,v in value.items() if k!="experiment"}!=expected.wire:raise ValueError("Local snapshot mismatch")
            return _snapshot(value)
        if value.get("kind")!="signed" or trusted_key is None:raise ValueError("Trusted approval key required")
        public_key(trusted_key).verify(base64.b64decode(value["signature"],validate=True),canonical(value["manifest"]))
        approved=value["manifest"].get("validation",{})
        if approved.get("passed") is not True or approved.get("criteria")!="prompt-control-v1" or not re.fullmatch(r"[a-f0-9]{64}",approved.get("report_sha256","")):raise ValueError("Unapproved release")
        experiment=value.get("experiment",{})
        if set(experiment)-{"prompt_experiment_id","prompt_experiment_group","prompt_experiment_config_sha256"} or any(not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}",str(x)) for x in experiment.values()):raise ValueError("Invalid experiment metadata")
        return _snapshot(value)
    except Exception:
        # Never include remote contents/URLs/signature in an exception message.
        raise ValueError("Invalid or untrusted prompt snapshot") from None

def current_snapshot():return _CONTEXT.get()

@contextmanager
def using_snapshot(snapshot):
    token=_CONTEXT.set(snapshot)
    try:yield snapshot
    finally:_CONTEXT.reset(token)

class ReleaseManager:
    def __init__(self,*,fetch:Callable[[],Awaitable[dict]],public_key,path:Path,initial:Snapshot,interval=60,timeout=8,load_persisted=True):
        self.fetch=fetch;self.public_key=public_key;self.path=Path(path);self.current=initial
        self.interval=interval;self.timeout=timeout;self.last_error=None;self.next_refresh=0.;self._lock=asyncio.Lock()
        if load_persisted and self.path.is_file():
            try:
                if self.path.stat().st_size>64000:raise ValueError("Oversized cache")
                self.current=validate_snapshot(json.loads(self.path.read_text(encoding="utf-8")),self.public_key)
            except Exception:self.last_error="InvalidPersistedRelease"
    async def refresh(self,*,force=False):
        if not force and time.monotonic()<self.next_refresh:return False
        async with self._lock:
            if not force and time.monotonic()<self.next_refresh:return False
            self.next_refresh=time.monotonic()+self.interval
            try:
                value=await asyncio.wait_for(self.fetch(),self.timeout)
                candidate=validate_snapshot(value,self.public_key)
                # A remote fetch may never downgrade validation to a local-shaped object.
                if value.get("kind")!="signed":raise ValueError("Unsigned remote release")
                self.path.parent.mkdir(parents=True,exist_ok=True)
                temporary=self.path.with_suffix(self.path.suffix+".tmp")
                temporary.write_text(candidate.serialized,encoding="utf-8");temporary.replace(self.path)
                changed=candidate.digest!=self.current.digest
                self.current=candidate;self.last_error=None
                return changed
            except Exception as exc:
                self.last_error=type(exc).__name__
                return False
    def status(self):
        return {**self.current.metadata(),"last_refresh_error":self.last_error,"refresh_interval_seconds":self.interval}
