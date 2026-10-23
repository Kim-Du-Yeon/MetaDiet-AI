import json
import pytest


def test_completion_preserves93_and_only_selects_remaining7(tmp_path):
    from scripts.eval.complete_clarification_flat import prepare,validate,build
    p=tmp_path/'run';plan=prepare(p);validate(p)
    assert plan['reused_complete_pairs']==93 and plan['remaining_pairs']==7
    rows=json.loads((p/'judges.json').read_text(encoding='utf-8'))['rows']
    assert len(rows)==93
    es,rs=build(p);assert len(es)==len(rs)==7
    assert all(e['format_contract']=='clarification-grade-flat-v1' for e in es)
    assert all(len(r['config']['response_json_schema']['properties'])==14 for r in rs)
    with pytest.raises(ValueError):prepare(p)
    rows[0]['grades']['a']['correct']=not rows[0]['grades']['a']['correct']
    j=json.loads((p/'judges.json').read_text(encoding='utf-8'));j['rows']=rows;(p/'judges.json').write_text(json.dumps(j),encoding='utf-8')
    with pytest.raises(ValueError):validate(p)


def test_completion_wont_resubmit_pending_batch(tmp_path):
    from scripts.eval.complete_clarification_flat import prepare,submit
    p=tmp_path/'run';prepare(p)
    (p/'batch-pending.json').write_text('{"collected":false}')
    with pytest.raises(ValueError,match='Pending'):submit(None,p,None)
