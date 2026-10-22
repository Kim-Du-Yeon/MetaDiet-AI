import json
from unittest.mock import patch
import pytest
from scripts.eval.followup_question_experiment import campaign_guard,seed_baseline,ROOT
from scripts.eval import eval_budget
from scripts.prompt_release_workflow import read

def test_campaign_cap_cannot_expand_existing_limits():
    seen=[]
    with patch.object(eval_budget,'TOTAL',17),patch.object(eval_budget,'LIMITS',{'judge':5}),patch.object(eval_budget,'install_transport_guard',lambda b,s:seen.append((eval_budget.TOTAL,eval_budget.LIMITS.copy()))):
        with campaign_guard({'total_limit_usd':10,'stage_caps':{'judge':9}}):eval_budget.install_transport_guard(None,'judge')
    assert seen==[(10,{'judge':5})]

def test_reuse_preserves_baseline_and_never_overwrites(tmp_path):
    base=read(ROOT/'docs/prompt_control/approved-release.json')
    c={'baseline':base,'snapshot':base}
    r=seed_baseline(ROOT/'docs/prompt_control/comparison',c,tmp_path)
    assert len(r['rows'])==100 and all(x['condition']=='v1' for x in r['rows'])
    from app.core.prompt_release_control import _snapshot
    assert all(x['prompt_metadata']['prompt_bundle_sha256']==_snapshot(r['prompt_snapshots']['v1']).digest for x in r['rows'])
    with pytest.raises(FileExistsError):seed_baseline(ROOT/'docs/prompt_control/comparison',c,tmp_path)

def test_reuse_rejects_other_baseline(tmp_path):
    base=read(ROOT/'docs/prompt_control/approved-release.json');base['manifest']['prompts']['team.compact_followup']['commit']='f'*64
    with pytest.raises(ValueError,match='identity'):seed_baseline(ROOT/'docs/prompt_control/comparison',{'baseline':base,'snapshot':base},tmp_path)
