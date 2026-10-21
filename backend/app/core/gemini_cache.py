"""Opt-in cache lifecycle. No provider I/O on import; content is never persisted.

Single-process coalescing only: keep disabled for horizontally scaled/private
production until a shared lease and durable deletion queue are configured.
"""
import asyncio
from dataclasses import dataclass
import hashlib
import hmac
import json
import time

@dataclass(frozen=True)
class CacheScope:
    owner: str
    conversation: str
    revision: int

class CachePool:
    def __init__(self,create,delete,*,secret,ttl=300,max_entries=128,clock=time.monotonic):
        if len(secret)<32 or not 1<=ttl<=3600 or max_entries<1:raise ValueError('Invalid cache policy')
        self.create=create;self.delete=delete;self.secret=secret;self.ttl=ttl
        self.max_entries=max_entries;self.clock=clock;self.entries={};self.pending={}
        self.failures={};self.epochs={};self.deletion_queue=set()
    def _owner(self,value):return hmac.new(self.secret,value.encode(),hashlib.sha256).hexdigest()
    def key(self,model,release,text,scope):
        identity=[model,release,hashlib.sha256(text.encode()).hexdigest()]
        identity += [self._owner(scope.owner),self._owner(scope.conversation),scope.revision] if scope else ['public']
        return hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    async def _delete(self,name):
        try:await asyncio.wait_for(self.delete(name),5)
        except Exception as exc:
            if getattr(exc,"code",getattr(exc,"status_code",None))==404:self.deletion_queue.discard(name)
            else:self.deletion_queue.add(name)
        else:self.deletion_queue.discard(name)
    async def cleanup(self):
        for key,entry in list(self.entries.items()):
            if entry['expires']<=self.clock():
                self.entries.pop(key,None);await self._delete(entry['name'])
        for name in list(self.deletion_queue):await self._delete(name)
        self.failures={k:v for k,v in self.failures.items() if v>self.clock()}
    async def invalidate(self,owner):
        token=self._owner(owner);self.epochs[token]=self.epochs.get(token,0)+1
        for key,entry in list(self.entries.items()):
            if entry['owner']==token:
                self.entries.pop(key,None);await self._delete(entry['name'])
    async def evict(self,name):
        for key,entry in list(self.entries.items()):
            if entry['name']==name:self.entries.pop(key,None)
        await self._delete(name)
    async def acquire(self,model,release,text,scope,*,eligible):
        if not eligible:return None
        if scope and (not scope.owner or not scope.conversation or scope.revision<0):raise ValueError('Invalid private scope')
        await self.cleanup()
        key=self.key(model,release,text,scope);entry=self.entries.get(key)
        if entry:return entry['name']
        if self.failures.get(key,0)>self.clock():return None
        if key not in self.pending:
            if len(self.pending)+len(self.entries)>=self.max_entries:return None
            self.pending[key]=asyncio.create_task(self._create(key,model,text,scope))
        task=self.pending[key]
        try:return await asyncio.shield(task)
        finally:
            if task.done():self.pending.pop(key,None)
    async def _create(self,key,model,text,scope):
        owner=self._owner(scope.owner) if scope else None;epoch=self.epochs.get(owner,0)
        try:
            name=await asyncio.wait_for(self.create(model,text,self.ttl),10)
            if not isinstance(name,str) or not name.startswith('cachedContents/'):raise ValueError('Invalid provider reference')
        except Exception:
            self.failures[key]=self.clock()+60;return None
        if self.epochs.get(owner,0)!=epoch:
            await self._delete(name);return None
        self.entries[key]={'name':name,'owner':owner,'expires':self.clock()+self.ttl}
        return name
    async def close(self):
        # Drain creation so a shutdown cannot strand a newly published reference.
        await asyncio.gather(*self.pending.values(),return_exceptions=True)
        for entry in list(self.entries.values()):await self._delete(entry['name'])
        self.entries.clear()

async def invoke_cached(pool,invoke,model,release,prefix,messages,*,eligible=False,scope=None):
    """Only cache the caller-audited prefix; dynamic current inputs remain messages.

    Callers must supply an authoritative CountTokens/break-even eligibility result.
    A missing cache is a definitive pre-generation failure; ambiguous timeouts and
    other provider failures propagate, avoiding an accidental second generation.
    """
    name=await pool.acquire(model,release,prefix,scope,eligible=eligible)
    full=[{'role':'system','content':prefix},*messages]
    if name is None:return await invoke(full)
    try:return await invoke(messages,cached_content=name)
    except Exception as exc:
        code=getattr(exc,'code',getattr(exc,'status_code',None))
        if code not in {400,404}:raise
        # Only an explicit cached-content error is safe to retry for a 400.
        if code==400 and 'cached' not in str(exc).lower():raise
        await pool.evict(name)
        return await invoke(full)

class GeminiCacheProvider:
    """Inject the existing google-genai client; no new credential or client pool."""
    def __init__(self,client):self.client=client
    async def create(self,model,prefix,ttl):
        result=await self.client.aio.caches.create(model=model,config={
            'system_instruction':prefix,'ttl':str(ttl)+'s'})
        return result.name
    async def delete(self,name):await self.client.aio.caches.delete(name=name)

def explicit_cache_break_even(*,tokens,reuses,ttl_seconds,input_per_million,read_per_million,storage_per_million_hour,minimum_tokens):
    """Estimates, not invoice amounts. Creation includes one full-price prefix write."""
    if tokens<minimum_tokens or reuses<1:return {'eligible':False,'reason':'minimum_or_reuse'}
    baseline=tokens*reuses*input_per_million/1e6
    explicit=tokens*(input_per_million+reuses*read_per_million+ttl_seconds/3600*storage_per_million_hour)/1e6
    return {'eligible':explicit<=baseline*.9,'reason':'economic' if explicit<=baseline*.9 else 'no_10_percent_saving',
            'ordinary_upper_estimate_usd':baseline,'explicit_estimate_usd':explicit,
            'baseline_note':'ordinary calls may already receive implicit cache discounts'}
