"""Deterministic experiment assignment; live activation requires separate approval."""
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from app.core.prompt_release_control import Snapshot, validate_snapshot

@dataclass(frozen=True)
class ExperimentPolicy:
    experiment_id:str
    salt:bytes
    variants:tuple[Snapshot,Snapshot]
    enabled:bool=False
    approved:bool=False
    percent_b:int=50
    unit:str="user"
    def __post_init__(self):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}",self.experiment_id) or len(self.salt)<32 or len(self.variants)!=2 or not 0<=self.percent_b<=100 or self.unit not in {"user","conversation"}:raise ValueError("Invalid frozen experiment")
    @property
    def identity(self):
        value=[self.experiment_id,hashlib.sha256(self.salt).hexdigest(),[s.digest for s in self.variants],self.percent_b,self.unit]
        return hashlib.sha256(json.dumps(value,separators=(",",":" )).encode()).hexdigest()
    def group(self,user,thread):
        payload=json.dumps([self.experiment_id,user,thread if self.unit=="conversation" else ""],separators=(",",":"))
        bucket=int.from_bytes(hmac.new(self.salt,payload.encode(),hashlib.sha256).digest()[:8],"big")%10000
        return "B" if bucket<self.percent_b*100 else "A"
    def assign(self,user,thread):
        if not self.enabled or not self.approved:return None
        label=self.group(user,thread);snapshot=self.variants[label=="B"]
        value=snapshot.wire
        value["experiment"]={"prompt_experiment_id":self.experiment_id,"prompt_experiment_group":label,"prompt_experiment_config_sha256":self.identity}
        # Metadata only; approval signature binds the immutable template bundle.
        return Snapshot(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False),snapshot.digest,snapshot.release)

def choose_snapshot(production,saved,*,pending,policy=None,user="",thread="",trusted_key=None):
    if pending:
        # Legacy pending flows were created before remote rollout with packaged v1.
        from app.core.prompt_release_control import local_snapshot
        return validate_snapshot(saved,trusted_key) if saved else local_snapshot("v1")
    if policy and policy.enabled and policy.approved:
        if saved and saved.get("experiment",{}).get("prompt_experiment_id")==policy.experiment_id:
            if saved.get("experiment",{}).get("prompt_experiment_config_sha256")!=policy.identity:
                raise ValueError("Experiment configuration changed; use a new experiment ID")
            return validate_snapshot(saved,trusted_key)
        return policy.assign(user,thread)
    return production
