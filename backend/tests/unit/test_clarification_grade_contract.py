"""Offline development fixtures; no model-quality or provider conformance claims."""
import copy,json,socket
from pathlib import Path
from unittest.mock import patch
import pytest


def sample(index=0):
    fields=['correct','faithful','fresh_current_values','unnecessary_request','focused_required_question','unsafe_commitment']
    return {side+'_'+key:(index+j+(side=='b'))%2==0 for side in ['a','b'] for j,key in enumerate(fields)}|{'a_reason':'Synthetic A '+str(index),'b_reason':'Synthetic B '+str(index)}


def test_development20_mixed_scores_roundtrip_without_inference():
    from scripts.eval.clarification_grade_contract import parse,request,CONTRACT_VERSION
    for i in range(20):
        value=sample(i);parsed=parse(json.dumps(value)).model_dump()
        for side in ['a','b']:
            assert parsed[side]=={k:value[side+'_'+k] for k in parsed[side]}
    req=request({'synthetic':'data'},'dev-only')
    schema=req['config']['response_json_schema']
    assert schema['type']=='object' and len(schema['properties'])==14
    assert set(schema['required'])==set(sample()) and schema['additionalProperties'] is False
    assert all(s['type'] in ['boolean','string'] for s in schema['properties'].values())
    assert CONTRACT_VERSION in req['config']['system_instruction']
    assert 'a_correct' in req['config']['system_instruction'] and 'array' in req['config']['system_instruction']


@pytest.mark.parametrize('mutation',['missing','extra','null','string','array','duplicate','nested'])
def test_strict_contract_rejects_ambiguous_or_incomplete_scores(mutation):
    from scripts.eval.clarification_grade_contract import parse
    v=sample()
    if mutation=='missing':v.pop('a_correct')
    if mutation=='extra':v['other']=True
    if mutation=='null':v['a_correct']=None
    if mutation=='string':v['b_faithful']='false'
    if mutation=='array':v={'a':list(v.values()),'b':list(v.values())}
    if mutation=='nested':v={'a':{},'b':{}}
    text=json.dumps(v)
    if mutation=='duplicate':text=text[:-1]+',"a_correct": false}'
    with pytest.raises(ValueError):parse(text)


def test_sdk_wire_preserves_flat_contract_without_network():
    from google import genai
    from scripts.eval.clarification_grade_contract import request,validate_wire
    from scripts.eval.batch_agentic_judges import requests_digest
    from scripts.eval.batch_clarification_resume import MODEL
    with patch.object(socket,'create_connection',side_effect=AssertionError('No network')):
        client=genai.Client(api_key='offline-placeholder-not-real')
        req=request({'synthetic':'data'},'dev-only')
        wire=json.loads(requests_digest(client,MODEL,[req]));client.close()
    validate_wire(wire,[req])
    damaged=copy.deepcopy(wire)
    damaged['batch']['inputConfig']['requests']['requests'][0]['request']['generationConfig'].pop('responseJsonSchema')
    with pytest.raises(ValueError):validate_wire(damaged,[req])
    for thinking in [None,{'thinking_level':'HIGH'},{'thinking_level':'LOW','thinkingBudget':4096}]:
        damaged=copy.deepcopy(wire)
        config=damaged['batch']['inputConfig']['requests']['requests'][0]['request']['generationConfig']
        if thinking is None:config.pop('thinkingConfig')
        else:config['thinkingConfig']=thinking
        with pytest.raises(ValueError):validate_wire(damaged,[req])


def test_saved31_arrays_stay_ungraded():
    from scripts.eval.clarification_grade_contract import parse
    root=Path(__file__).resolve().parents[3]/'docs/prompt_control/clarification-balanced/execution-v2/retry-025'
    rows=json.loads((root/'unresolved.json').read_text(encoding='utf-8'))
    assert len(rows)==31
    for row in rows:
        raw=json.loads((root/row['raw_path']).read_text(encoding='utf-8'))
        with pytest.raises(ValueError):parse(raw['text'])
