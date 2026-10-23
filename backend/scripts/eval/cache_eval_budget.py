"""Budgeted Flash cache experiments; opt-in, no changes to ordinary eval guard.

Creation is conservatively charged at full prefix input + full TTL storage. This
is an upper estimate, not a claim that Google invoices a separate write fee.
"""
import json,re,hashlib
from scripts.eval.eval_budget import BudgetStop,request_bound

MODEL='gemini-3.8-flash'
class CacheAccounting:
    def __init__(self):self.names={};self.events=[]
    def bound(self,method,path,body):
        if method.lower() in {'get','delete'} or path.endswith(':countTokens'):return 0
        if path.rstrip('/').endswith('cachedContents'):
            model=body.get('model','').removeprefix('models/');ttl=body.get('ttl','')
            if model!=MODEL or not re.fullmatch(r'\d+s',ttl) or not 1<=int(ttl[:-1])<=300:raise BudgetStop('Unpriced cache model/TTL')
            encoded=json.dumps(body,ensure_ascii=False).encode()
            if any(key in encoded for key in [b'"inlineData"',b'"fileData"',b'"tools"']):raise BudgetStop('Only text cache priced')
            tokens=len(encoded)+2048
            return tokens*(.75+int(ttl[:-1])/3600*.5)/1e6
        normal=path.replace(':streamGenerateContent',':generateContent').split('?')[0]
        if body.get('cachedContent'):
            cache=self.names.get(body['cachedContent'])
            if cache is None or not normal.startswith('models/'+cache['model']+':'):raise BudgetStop('Unknown or mismatched cached prefix')
            return request_bound(normal,{k:v for k,v in body.items() if k!='cachedContent'})+cache['tokens']*.75/1e6
        return request_bound(normal,body)
    def actual(self,path,request,response):
        try:
            value=json.loads(response.body)
            if path.rstrip('/').endswith('cachedContents'):
                tokens=value['usageMetadata']['totalTokenCount'];name=value['name'];ttl=int(request['ttl'][:-1])
                if type(tokens) is not int or tokens<0 or not isinstance(name,str):return None
                self.names[name]={'model':MODEL,'tokens':tokens}
                write=tokens*.75/1e6;storage=tokens*ttl/3600*.5/1e6
                self.events.append({'cache_id_sha256':hashlib.sha256(name.encode()).hexdigest(),'tokens':tokens,'ttl_seconds':ttl,'creation_input_upper_usd':write,'storage_full_ttl_upper_usd':storage})
                return write+storage
            usage=value['usageMetadata'];incoming=usage['promptTokenCount'];cached=usage.get('cachedContentTokenCount',0);outgoing=usage.get('candidatesTokenCount',0)+usage.get('thoughtsTokenCount',0)
            if any(type(n) is not int or n<0 for n in [incoming,cached,outgoing]) or cached>incoming:return None
            if 'models/'+MODEL+':' not in path:return None
            return ((incoming-cached)*.75+cached*.075+outgoing*3.75)/1e6
        except (ValueError,TypeError,KeyError,AttributeError):return None

def install_cache_guard(budget,stage,account,client_class=None):
    if client_class is None:
        from google.genai._api_client import BaseApiClient
        client_class=BaseApiClient
    sync=client_class.request;asynchronous=client_class.async_request;streaming=client_class.async_request_streamed
    def options(value):
        if value is not None and hasattr(value,'model_dump'):value=value.model_dump(exclude_none=True)
        return {**(value or {}),'retry_options':{'attempts':1}}
    def reserve(method,path,body):
        bound=account.bound(method,path,body)
        return budget.reserve(stage,bound) if bound else None
    def settle(ticket,path,body,response):
        if ticket is None:return
        actual=account.actual(path,body,response) if response is not None else None
        budget.settle(ticket,actual)
        if response is not None and actual is None:raise BudgetStop('Cache experiment usage missing; conservative reservation retained')
    def guarded(client,method,path,body,http_options=None):
        ticket=reserve(method,path,body)
        try:response=sync(client,method,path,body,options(http_options))
        except BaseException:
            settle(ticket,path,body,None);raise
        settle(ticket,path,body,response);return response
    async def guarded_async(client,method,path,body,http_options=None):
        ticket=reserve(method,path,body)
        try:response=await asynchronous(client,method,path,body,options(http_options))
        except BaseException:
            settle(ticket,path,body,None);raise
        settle(ticket,path,body,response);return response
    async def guarded_stream(client,method,path,body,http_options=None):
        ticket=reserve(method,path,body)
        try:source=await streaming(client,method,path,body,options(http_options))
        except BaseException:
            settle(ticket,path,body,None);raise
        async def iterator():
            last_usage=None;complete=False
            try:
                async for response in source:
                    try:
                        if 'usageMetadata' in json.loads(response.body):last_usage=response
                    except (ValueError,TypeError):pass
                    yield response
                complete=True
            finally:
                if ticket:
                    amount=account.actual(path,body,last_usage) if complete and last_usage else None
                    budget.settle(ticket,amount)
                    if complete and amount is None:raise BudgetStop('Final stream usage missing; no further calls')
        return iterator()
    def unsupported(*args,**kwargs):raise BudgetStop('Synchronous streaming not priced')
    client_class.request=guarded;client_class.async_request=guarded_async
    client_class.async_request_streamed=guarded_stream;client_class.request_streamed=unsupported
