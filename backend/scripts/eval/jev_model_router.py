"""Experimental model selector only. Not wired to production request routing."""
from typing import Literal
import math
from pydantic import BaseModel,ConfigDict,Field


class RoutingRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    task: Literal['agent','extraction','classification','query_translation','vision','eval']
    text: str=Field(max_length=4000)
    deterministic: bool=False
    pending: bool=False
    tools_required: bool=False


async def select_model(request,*,mode,settings,client,budget):
    if mode not in {'rules','jev'}: raise ValueError('Unknown router mode')
    if request.deterministic:
        return {'status':'completed','band':'none','model':None,'source':'policy','jev_attempted':False}
    if request.task in {'vision','eval'}:
        model=settings.gemini_vision_model if request.task=='vision' else settings.gemini_eval_model
        return {'status':'completed','band':request.task,'model':model,'source':'policy','jev_attempted':False}
    if request.task=='agent' or request.pending or request.tools_required:
        return {'status':'completed','band':'standard','model':settings.gemini_model,'source':'policy','jev_attempted':False}
    mapping={'fast':settings.gemini_simple_model,'standard':settings.gemini_model}
    if mode=='rules':
        return {'status':'completed','band':'fast','model':mapping['fast'],'source':'rules','jev_attempted':False}
    decision=await client.choose(state={'task':request.task,'synthetic_request':request.text},
        candidates={'fast':'Unambiguous bounded extraction, classification or translation; no unresolved references or conflicting constraints.',
                    'standard':'Ambiguous prior references, conflicting constraints or reasoning beyond a bounded simple task. Prefer this when uncertain.'},
        budget=budget,min_confidence=.9)
    confident=(type(decision.confidence) in (int,float) and
        math.isfinite(decision.confidence) and .9<=decision.confidence<=1)
    accepted=decision.choice in mapping and decision.fallback_reason is None and confident
    band=decision.choice if accepted else 'standard'
    return {'status':'completed' if accepted else 'fallback','band':band,'model':mapping[band],
            'source':'jev' if accepted else 'fallback','jev_attempted':True,
            'fallback_reason':None if accepted else decision.fallback_reason or
                ('low_confidence' if not confident else 'invalid_choice'),
            'decision':decision.event()}
