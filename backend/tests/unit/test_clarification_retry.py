import json
import pytest
from scripts.eval.clarification_execution import FOLDER
from scripts.eval.retry_clarification_grades import prepare,smoke_passed,increment_ceiling

def test_retry_prepares_only45_and_preserves55(tmp_path):
 p=tmp_path/'run';plan=prepare(p)
 assert plan['reused_complete_pairs']==55 and plan['pending_pairs']==45
 assert len(plan['smoke_ids'])==2
 old=json.loads((FOLDER/'offline-recovery/judges.json').read_text(encoding='utf-8'));new=json.loads((p/'judges.json').read_text(encoding='utf-8'))
 assert new['rows']==[r for r in old['rows'] if r['status']=='completed']
 assert not smoke_passed(p)
 with pytest.raises(ValueError):prepare(p)

def test_increment_cap_cannot_be_raised():
 assert increment_ceiling({'baseline_usd':9.533327,'additional_cap_usd':.25})==pytest.approx(9.783327)
 for plan in [{'baseline_usd':9.533327,'additional_cap_usd':.26},{'baseline_usd':9.,'additional_cap_usd':.25}]:
  with pytest.raises(ValueError):increment_ceiling(plan)

def test_rest_requires_both_complete_smoke_pairs(tmp_path):
 p=tmp_path/'run';plan=prepare(p);path=p/'judges.json';j=json.loads(path.read_text(encoding='utf-8'))
 j['rows'].append({'case_id':plan['smoke_ids'][0],'status':'completed'})
 path.write_text(json.dumps(j),encoding='utf-8');assert not smoke_passed(p)
 j['rows'].append({'case_id':plan['smoke_ids'][1],'status':'failed'})
 path.write_text(json.dumps(j),encoding='utf-8');assert not smoke_passed(p)

def test_atomic_reservation_keeps_history_and_enforces_increment(tmp_path,monkeypatch):
 from scripts.eval import eval_budget as eb
 monkeypatch.setattr(eb,'TOTAL',20.)
 monkeypatch.setattr(eb,'LIMITS',{'browser':20.,'judge':1.})
 b=eb.Budget(tmp_path/'ledger.sqlite');b.reserve('browser',9.533327)
 monkeypatch.setattr(eb,'TOTAL',increment_ceiling({'baseline_usd':9.533327,'additional_cap_usd':.25}))
 b.reserve('judge',.2)
 with pytest.raises(eb.BudgetStop):b.reserve('judge',.050002)
 assert b.summary()['committed_usd']==pytest.approx(9.733327)
 assert b.summary()['stopped']

def test_rest_rejects_before_installing_paid_transport(tmp_path,monkeypatch):
 from argparse import Namespace
 from scripts.eval import retry_clarification_grades as runner
 p=tmp_path/'run';prepare(p)
 monkeypatch.setattr(runner,'install_budget',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('No transport allowed')))
 with pytest.raises(ValueError,match='Smoke'):runner.main(Namespace(action='rest',folder=p,allow_paid=True))

@pytest.mark.parametrize('ids',[[],['another-case'],['another-a','another-b']])
def test_smoke_case_list_cannot_be_changed(tmp_path,ids):
 from scripts.eval.retry_clarification_grades import validate
 p=tmp_path/'run';prepare(p);path=p/'retry-plan.json';plan=json.loads(path.read_text(encoding='utf-8'));plan['smoke_ids']=ids;path.write_text(json.dumps(plan),encoding='utf-8')
 assert not smoke_passed(p)
 with pytest.raises(ValueError,match='smoke'):validate(p)
