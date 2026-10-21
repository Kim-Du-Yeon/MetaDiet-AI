import sys
from pathlib import Path
import pytest
from langchain_core.documents import Document
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts/eval"))
from controlled_hybrid_support import common_answer_result, alternating_conditions, enable_campaign_budget

def test_same_answer_guidance_and_context_for_both_conditions():
    docs=[Document(page_content="original evidence",metadata={"source_file":"a.pdf","page":2})]
    source={"context_docs":docs,"docs":docs,"grounded":True,"max_score":.8,"answer_guidance":"condition-specific instructions"}
    left=common_answer_result(source)
    right=common_answer_result({**source,"agentic":{"rounds":2}})
    assert left["context"]==right["context"]
    assert left["answer_guidance"]==right["answer_guidance"]
    assert "condition-specific" not in left["answer_guidance"]
    assert source["answer_guidance"]=="condition-specific instructions"

def test_balanced_order():
    orders=[alternating_conditions(i) for i in range(100)]
    assert sum(o[0]=="baseline" for o in orders)==50
    assert all(set(o)=={"baseline","agentic"} for o in orders)

def test_budget_requires_explicit_paid_opt_in(monkeypatch):
    import eval_budget
    monkeypatch.setattr(eval_budget,"TOTAL",5.)
    monkeypatch.setattr(eval_budget,"LIMITS",dict(eval_budget.LIMITS))
    with pytest.raises(ValueError): enable_campaign_budget(False)
    assert eval_budget.TOTAL==5.
    enable_campaign_budget(True)
    assert eval_budget.TOTAL==15.
    assert sum(eval_budget.LIMITS.values())==pytest.approx(15.)
