"""Candidate format-only judge contract. No provider calls or production activation."""
import copy
import json
from scripts.eval.batch_clarification_resume import Grade,Pair
from scripts.eval.clarification_execution import RUBRIC

CONTRACT_VERSION='clarification-grade-flat-v1'
FIELDS=tuple(Grade.model_fields)
KEYS=tuple(side+'_'+key for side in ('a','b') for key in FIELDS)
FORMAT_INSTRUCTION=(
    '\nOutput contract '+CONTRACT_VERSION+': return exactly one JSON object. '
    'Each answer has its own explicitly named fields: '+', '.join(KEYS)+'. '
    'All fields ending in _reason are strings; all other fields are JSON booleans. '
    'Do not return any array, positional values, nested a/b objects, nulls, extra keys or markdown. '
    'This specifies representation only: apply the original rubric unchanged, including negative findings.'
)


def schema():
    return {'type':'object','properties':{
        side+'_'+key:{'type':'string' if key=='reason' else 'boolean'}
        for side in ('a','b') for key in FIELDS},
        'required':list(KEYS),'additionalProperties':False}


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON key')
        result[key]=value
    return result


def parse(text):
    value=json.loads(text,object_pairs_hook=_unique_object)
    if not isinstance(value,dict) or set(value)!=set(KEYS):
        raise ValueError('Complete named flat fields required')
    # Strict Pair validation rejects null, coerced booleans and non-string reasons.
    return Pair.model_validate({side:{key:value[side+'_'+key] for key in FIELDS}
                                for side in ('a','b')})


def request(payload,key):
    if not isinstance(payload,dict) or not isinstance(key,str) or not key:
        raise ValueError('Explicit object payload and key required')
    return {'contents':[{'role':'user','parts':[{'text':json.dumps(payload,ensure_ascii=False)}]}],
            'metadata':{'key':key},'config':{
                'system_instruction':RUBRIC+FORMAT_INSTRUCTION,'temperature':0,
                'max_output_tokens':2048,'thinking_config':{'thinking_level':'low'},
                'response_mime_type':'application/json','response_json_schema':schema()}}


def validate_wire(wire,requests):
    """Check the installed native Batch serializer actually transmits the contract."""
    try:actual=wire['batch']['inputConfig']['requests']['requests']
    except (KeyError,TypeError) as exc:raise ValueError('Missing native Batch requests') from exc
    if len(actual)!=len(requests):raise ValueError('Batch request count changed')
    for entry,expected in zip(actual,requests):
        body=entry.get('request',{});config=body.get('generationConfig',{})
        instructions=body.get('systemInstruction',{}).get('parts',[])
        if (entry.get('metadata')!=expected['metadata'] or body.get('contents')!=expected['contents']
            or config.get('responseJsonSchema')!=schema()
            or config.get('responseMimeType')!='application/json'
            or config.get('maxOutputTokens')!=2048 or config.get('temperature')!=0
            or config.get('thinkingConfig') not in ({'thinking_level':'LOW'},{'thinkingLevel':'LOW'})
            or instructions!=[{'text':RUBRIC+FORMAT_INSTRUCTION}]):
            raise ValueError('Native Batch format/payload contract changed')
    return copy.deepcopy(wire)
