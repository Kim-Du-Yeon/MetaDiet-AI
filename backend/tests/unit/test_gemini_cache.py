import asyncio
import pytest
from app.core.gemini_cache import CachePool, CacheScope

@pytest.mark.asyncio
async def test_coalesces_creation_and_scopes_by_release_owner_revision():
    created=[];deleted=[]
    async def create(model,text,ttl):
        await asyncio.sleep(0);created.append(text);return 'cachedContents/'+str(len(created))
    async def delete(name):deleted.append(name)
    pool=CachePool(create,delete,secret=b'x'*32)
    scope=CacheScope('user-a','thread-a',0)
    values=await asyncio.gather(*(pool.acquire('model','release','prefix',scope,eligible=True) for _ in range(10)))
    assert len(set(values))==1 and len(created)==1
    assert await pool.acquire('model','release2','prefix',scope,eligible=True)!=values[0]
    assert await pool.acquire('model','release','prefix',CacheScope('user-b','thread-a',0),eligible=True)!=values[0]
    await pool.invalidate('user-a')
    assert len(deleted)==2

@pytest.mark.asyncio
async def test_ineligible_prefix_never_created_and_failure_is_bounded():
    calls=[]
    async def create(*args):calls.append(1);raise RuntimeError('provider')
    async def delete(name):pass
    pool=CachePool(create,delete,secret=b'x'*32)
    assert await pool.acquire('m','r','p',None,eligible=False) is None
    for _ in range(3):assert await pool.acquire('m','r','p',None,eligible=True) is None
    assert len(calls)==1

@pytest.mark.asyncio
async def test_invalidation_racing_creation_does_not_publish_private_cache():
    started=asyncio.Event();finish=asyncio.Event();deleted=[]
    async def create(*args):started.set();await finish.wait();return 'cachedContents/one'
    async def delete(name):deleted.append(name)
    pool=CachePool(create,delete,secret=b'x'*32)
    task=asyncio.create_task(pool.acquire('m','r','p',CacheScope('a','t',0),eligible=True))
    await started.wait();await pool.invalidate('a');finish.set()
    assert await task is None and deleted==['cachedContents/one']

@pytest.mark.asyncio
async def test_invalid_reference_falls_back_once_but_timeout_does_not_duplicate():
    from app.core.gemini_cache import invoke_cached
    calls=[]
    class Missing(Exception):code=404
    async def invoke(messages,**kwargs):
        calls.append(kwargs)
        if kwargs:raise Missing()
        return 'fresh'
    deleted=[]
    async def create(*args):return 'cachedContents/one'
    async def delete(name):deleted.append(name)
    pool=CachePool(create,delete,secret=b'x'*32)
    assert await invoke_cached(pool,invoke,'m','r','prefix',[{'role':'user','content':'fresh current question'}],eligible=True)=='fresh'
    assert len(calls)==2 and deleted==['cachedContents/one']
    async def timeout(*args,**kwargs):calls.append(kwargs);raise TimeoutError()
    with pytest.raises(TimeoutError):await invoke_cached(pool,timeout,'m','r','prefix',[],eligible=True)
    assert len(calls)==3

@pytest.mark.asyncio
async def test_expired_provider_reference_is_successful_cleanup_not_retry_queue():
    class Missing(Exception):code=404
    async def create(*args):return 'cachedContents/gone'
    async def delete(name):raise Missing()
    pool=CachePool(create,delete,secret=b'x'*32)
    await pool._delete('cachedContents/gone')
    assert not pool.deletion_queue

@pytest.mark.asyncio
async def test_hundred_synthetic_mutations_keep_dynamic_inputs_and_isolation():
    from app.core.gemini_cache import invoke_cached
    created=[];observed=[]
    async def create(model,text,ttl):
        created.append(text);return 'cachedContents/'+str(len(created))
    async def delete(name):pass
    async def invoke(messages,**kwargs):
        observed.append((messages,kwargs));return messages[-1]['content']
    pool=CachePool(create,delete,secret=b'x'*32)
    for number in range(100):
        owner='synthetic-'+str(number%2)
        revision=number//2
        current='current:'+str(number)+':operation:'+['save','edit','delete','goal','new_day'][number%5]
        scope=CacheScope(owner,'thread',revision)
        result=await invoke_cached(pool,invoke,'m','r','static role only',[{'role':'user','content':current}],eligible=True,scope=scope)
        assert result==current
        assert pool.key('m','r','static role only',scope)!=pool.key('m','r','static role only',CacheScope('other','thread',revision))
        await pool.invalidate(owner)
    assert len(observed)==100 and len(created)==100
    assert set(created)=={'static role only'}
    await pool.close()
