import json
from argparse import Namespace
from types import SimpleNamespace as N
from unittest.mock import patch
import pytest


def test_prepare_keeps69_and_fixed_two(tmp_path):
    from scripts.eval.clarification_flat_retry import prepare,validate,smoke_passed,SMOKE_IDS,build
    p=tmp_path/'run';prepare(p);validate(p)
    j=json.loads((p/'judges.json').read_text(encoding='utf-8'))
    assert len(j['rows'])==69 and not smoke_passed(p)
    es,rs=build(p);assert len(es)==len(rs)==31
    assert set(SMOKE_IDS)<={e['key'] for e in es}
    assert all(len(r['config']['response_json_schema']['properties'])==14 for r in rs)
    with pytest.raises(ValueError):prepare(p)
    plan=json.loads((p/'flat-plan.json').read_text());plan['smoke_ids']=[]
    (p/'flat-plan.json').write_text(json.dumps(plan))
    with pytest.raises(ValueError):validate(p)


def test_rest_rejects_before_transport(tmp_path,monkeypatch):
    from scripts.eval import clarification_flat_retry as m
    p=tmp_path/'run';m.prepare(p)
    monkeypatch.setattr(m,'install_budget',lambda *a:(_ for _ in ()).throw(AssertionError('No transport')))
    with pytest.raises(ValueError,match='Smoke'):m.main(Namespace(action='rest',folder=p,allow_paid=True))


def test_ceiling_fixed_and_pending_prevents_submission(tmp_path):
    from scripts.eval import clarification_flat_retry as m
    assert m.CEILING==pytest.approx(9.783327)
    p=tmp_path/'run';m.prepare(p)
    (p/'batch-pending.json').write_text(json.dumps({'collected':False}))
    with pytest.raises(ValueError,match='Pending'):m.submit(N(),p,N(),'smoke')


def test_atomic_increment_does_not_reset_old_usage(tmp_path,monkeypatch):
    from scripts.eval import eval_budget as e
    from scripts.eval.clarification_flat_retry import CEILING,BASELINE
    monkeypatch.setattr(e,'TOTAL',20);monkeypatch.setattr(e,'LIMITS',{'judge':20})
    b=e.Budget(tmp_path/'budget');b.reserve('judge',BASELINE)
    monkeypatch.setattr(e,'TOTAL',CEILING)
    with pytest.raises(e.BudgetStop):b.reserve('judge',.108479)
    assert b.summary()['committed_usd']==pytest.approx(BASELINE)
