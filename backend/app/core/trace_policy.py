"""Fail-closed trace bodies and standard text-token list-price estimates.

Only explicitly attested, local synthetic runs may retain prose. Production
retains structure, not free text or health values. This is not a PII classifier.
"""
from __future__ import annotations
import os
import re
from datetime import date
from functools import lru_cache
from langsmith import Client, tracing_context

REDACTED = '[REDACTED]'
STRUCTURE = {'messages','message','kwargs','content','text','generations','generation_info',
             'tool_calls','tool_call_chunks','args','arguments','input','output','response','type','role'}
# Standard text inference, USD / million tokens; verified 2026-10-23.
# Expire deliberately rather than silently using stale promotional prices.
PRICES = {'gemini-3.8-flash': (.75,3.75,.075),
          'gemini-3.1-flash-lite': (.25,1.5,.025),
          'gemini-3.5-flash-lite': (.30,2.5,.03),
          'gemini-3.1-pro-preview': (2.,12.,.2)}


def trace_mode(env=None):
    env = os.environ if env is None else env
    if env.get('RENDER') or env.get('APP_ENV','').lower() in {'production','staging'}:
        return 'production'
    return 'synthetic' if (env.get('TRACE_DATA_MODE') == 'synthetic' and
                           env.get('TRACE_SYNTHETIC_ONLY') == 'true') else 'production'


def mask_body(value):
    if isinstance(value, dict):
        result = {k: mask_body(v) for k,v in value.items() if k in STRUCTURE}
        if len(result) != len(value): result['redacted_fields'] = True
        return result
    if isinstance(value, (list,tuple)): return [mask_body(v) for v in value]
    return REDACTED


def safe_metadata(value):
    result = {}
    for key,val in (value or {}).items():
        if key == 'thread_id' and isinstance(val,str) and re.fullmatch(r'thread-[a-f0-9]{24}',val):
            result[key]=val
        elif key in {'ls_model_name','model_name'} and val in PRICES:
            result[key]=val
        elif key == 'ls_provider' and val in {'google_genai','google','google_vertexai'}:
            result[key]=val
        elif key in {'request_id','attempt_id','build_commit','prompt_release','prompt_bundle_hash',
                     'system_instruction_sha256','prompt_release_commit','prompt_release_hash',
                     'prompt_bundle_sha256','prompt_scope','prompt_source','prompt_id','prompt_version','prompt_sha256',
                     'prompt_experiment_id','prompt_experiment_group','prompt_experiment_config_sha256',
                     'model_task','model_role','experiment_id','experiment_group'}:
            if isinstance(val,str) and re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}',val): result[key]=val
    for key in ('prompt_commit_ids','prompt_hashes'):
        values=(value or {}).get(key)
        if isinstance(values,dict):
            from app.core.prompt_release_control import REPOS
            result[key]={k:v for k,v in values.items() if k in REPOS and
                         (v is None or isinstance(v,str) and re.fullmatch(r'[a-f0-9]{64}',v))}
    return result


def priced_usage(model, usage, *, day=None):
    day = day or date.today()
    if model not in PRICES or day > date(2026,12,31) or not isinstance(usage,dict): return None
    names=('input_tokens','output_tokens','total_tokens')
    if any(type(usage.get(k)) is not int or usage[k]<0 for k in names): return None
    incoming,outgoing,total=(usage[k] for k in names)
    details=usage.get('input_token_details') or {}
    output_details=usage.get('output_token_details') or {}
    cached=details.get('cache_read',0)
    if type(cached) is not int or not 0<=cached<=incoming or incoming+outgoing!=total: return None
    if any(details.get(k,0) for k in ('audio','image','video','cache_creation')): return None
    # Pro long-context has different rates; never silently apply short-context rates.
    if model=='gemini-3.1-pro-preview' and incoming>200000: return None
    rate_in,rate_out,rate_cache=PRICES[model]
    result={k:usage[k] for k in names}
    result['input_token_details']={'cache_read':cached}
    reasoning=output_details.get('reasoning',0)
    if type(reasoning) is not int or not 0<=reasoning<=outgoing: return None
    result['output_token_details']={'reasoning':reasoning}
    result['input_cost']=((incoming-cached)*rate_in+cached*rate_cache)/1e6
    result['output_cost']=outgoing*rate_out/1e6 # SDK output already includes thinking
    result['total_cost']=result['input_cost']+result['output_cost']
    return result


def observed_usage(value):
    if not isinstance(value,dict): return None
    result={k:value[k] for k in ('input_tokens','output_tokens','total_tokens')
            if type(value.get(k)) is int and value[k]>=0}
    for key,allowed in [('input_token_details',('cache_read','audio','image','video')),('output_token_details',('reasoning','audio','image'))]:
        details=value.get(key)
        if isinstance(details,dict):
            result[key]={k:details[k] for k in allowed if type(details.get(k)) is int and details[k]>=0}
    return result or None


def synthetic_body(value):
    if isinstance(value,dict):
        return {k:REDACTED if re.search(r'key|password|secret|authorization|credential|signature',k,re.I)
                else synthetic_body(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [synthetic_body(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'(?i)Bearer\s+[A-Za-z0-9._-]+','Bearer [REDACTED]',value)
        for key,secret in os.environ.items():
            if re.search(r'API_KEY|SECRET|PASSWORD|SERVICE_KEY',key) and len(secret)>8:
                value=value.replace(secret,REDACTED)
    return value


def safe_name(value):
    allowed={'LangGraph','ChatGoogleGenerativeAI','ChatPromptTemplate','RunnableSequence',
             'supervisor','meal','goal','evidence','save_chat','save_pending_chat','confirm',
             'load_state','diet_logger','strategy','inbody','goal_manager','reporter','meal_planner',
             'meal_plan','validator','edit','off_topic','after_task','trace-smoke'}
    return value if value in allowed else 'trace'


def sanitize_run(data, mode):
    """Sanitize BEFORE the SDK queue, including errors/serialized invocation params."""
    result=dict(data)
    metadata=(data.get('extra') or {}).get('metadata') or {}
    clean=safe_metadata(metadata)
    clean['trace_data_mode']=mode
    model=metadata.get('ls_model_name') or metadata.get('model_name')
    usage=priced_usage(model,metadata.get('usage_metadata'))
    if usage is not None:
        clean['usage_metadata']=usage
        clean['cost_basis']='standard_text_list_price_estimate_2026-10-23'
    elif metadata.get('ls_model_name') or metadata.get('usage_metadata'):
        clean['cost_basis']='unknown_or_unsupported'
    if usage is None:
        observed=observed_usage(metadata.get('usage_metadata'))
        if observed: clean['usage_metadata']=observed
    result['extra']={'metadata':clean}
    if 'name' in result: result['name']=safe_name(result['name'])
    for field in ('inputs','outputs'):
        if field in result and result[field] is not None:
            result[field]=synthetic_body(result[field]) if mode=='synthetic' else mask_body(result[field])
    if result.get('error'): result['error']='execution_failed_details_redacted'
    if 'serialized' in result: result['serialized']={}
    if 'events' in result:
        result['events']=[{'name':e.get('name') if e.get('name') in {'start','end','new_token'} else 'event',
                          'time':e.get('time')} for e in (result['events'] or [])]
    result.pop('attachments',None)
    if 'tags' in result: result['tags']=['metadiet-trace-v1',mode]
    return result


class PolicyClient(Client):
    """Use the public create/update API boundary; never patch LangSmith internals."""
    def __init__(self, *, mode='production', **kwargs):
        if mode not in {'production','synthetic'}: raise ValueError('Unknown trace mode')
        if mode=='synthetic' and trace_mode()!='synthetic':
            raise ValueError('Synthetic traces require local synthetic-only attestation')
        self.trace_data_mode = mode
        super().__init__(hide_inputs=False,hide_outputs=False,hide_metadata=False,
                         omit_traced_runtime_info=True, **kwargs)

    def create_run(self, name, inputs, run_type, **kwargs):
        data=sanitize_run({'inputs':inputs,**kwargs},self.trace_data_mode)
        return super().create_run(safe_name(name),run_type=run_type,**data)

    def update_run(self, run_id, **kwargs):
        return super().update_run(run_id,**sanitize_run(kwargs,self.trace_data_mode))


@lru_cache(maxsize=1)
def runtime_client():
    return PolicyClient(mode='production',api_key=os.getenv('LANGSMITH_API_KEY'),
                        api_url=os.getenv('LANGSMITH_ENDPOINT','https://api.smith.langchain.com'))


class TracePolicyMiddleware:
    """ASGI context also covers background SSE tasks; HTTP never enables raw mode."""
    def __init__(self,app): self.app=app
    async def __call__(self,scope,receive,send):
        enabled=os.getenv('LANGSMITH_TRACING','true').lower()=='true' and bool(os.getenv('LANGSMITH_API_KEY'))
        if not enabled:
            with tracing_context(enabled=False): await self.app(scope,receive,send)
            return
        with tracing_context(client=runtime_client(),enabled=True,
                             project_name=os.getenv('LANGSMITH_PROJECT','diet-agent')):
            await self.app(scope,receive,send)


def synthetic_trace_context(project_name):
    """Explicit opt-in for synthetic-only eval entry points (not HTTP requests)."""
    if not re.fullmatch(r'metadiet-synthetic-[a-zA-Z0-9_-]{1,64}',project_name):
        raise ValueError('Use a dedicated metadiet-synthetic-* project')
    client=PolicyClient(mode='synthetic',api_key=os.getenv('LANGSMITH_API_KEY'),
                        api_url=os.getenv('LANGSMITH_ENDPOINT','https://api.smith.langchain.com'))
    return tracing_context(enabled=True,client=client,project_name=project_name)
