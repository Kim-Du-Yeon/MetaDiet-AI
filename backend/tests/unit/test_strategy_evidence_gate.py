import pytest
from app.core.service_clock import service_today

def fixture():
    profile = {'region': 'KR', 'age': 30, 'weight_kg': 70,
               'policy_population':'adult', 'policy_conditions':''}
    evidence = {'source': 'policy.pdf', 'page': '2', 'excerpt': 'Reviewed bounds', 'document_sha256': 'a'*64}
    payload = dict(daily_calories=1800, protein_g=100, carbs_g=230, fat_g=53,
                   evidence=[evidence])
    claims = [dict(id=key, claim_key=key, family=key, authority='national_guideline',
        region='KR', population='adult', conditions='', year=2025, unit=unit,
        low=low, high=high, review_status='approved', reviewer='synthetic-test', **evidence)
        for key,unit,low,high in [('daily_calories','kcal_per_day',1700,1900),
          ('protein_g','g_per_day',90,120),('carbs_g','g_per_day',200,250),('fat_g','g_per_day',40,65)]]
    return payload, profile, claims

def gate(payload,profile,claims):
    from app.rag.strategy_evidence import evaluate_strategy
    return evaluate_strategy(payload,profile,claims)

def test_reviewed_bounds_generate_traceable_receipt():
    p,u,c=fixture(); result=gate(p,u,c)
    assert result['status']=='approved'
    assert len(result['decisions'])==4
    assert result['policy_version']


def test_pdf_whitespace_does_not_break_reviewed_excerpt_match():
    p,u,c=fixture()
    p['evidence'][0]['excerpt']='Reviewed\n\t bounds'
    assert gate(p,u,c)['status']=='approved'

@pytest.mark.parametrize('fault',['empty','unreviewed','conflict','old','unit','outside','hash','population','unknown_context'])
def test_uncertain_evidence_cannot_authorize_numeric_change(fault):
    p,u,c=fixture()
    if fault=='empty': c=[]
    if fault=='unreviewed': c[0]['review_status']='candidate'
    if fault=='conflict': c.append({**c[0],'id':'other','family':'other','low':1500,'high':1600})
    if fault=='old': c.append({**c[0],'id':'new','year':2026,'excerpt':'New bounds'})
    if fault=='unit': c[0]['unit']='unknown_unit'
    if fault=='outside': p['daily_calories']=1300
    if fault=='hash': p['evidence'][0]['document_sha256']='b'*64
    if fault=='population': u['age']=17
    if fault=='unknown_context': u.pop('policy_population'); u.pop('policy_conditions')
    with pytest.raises(ValueError): gate(p,u,c)

async def test_repository_rechecks_policy_before_any_strategy_write():
    from app.db.proposals import ProposalRepository
    from unittest.mock import AsyncMock
    p,u,c=fixture()
    p.update(kind='strategy',effective_date=service_today().isoformat(),based_on_strategy_id=None,
             strategy_note='test',policy_version='old')
    conn=AsyncMock()
    conn.execute.return_value.fetchone.return_value=u
    with pytest.raises(ValueError):
        await ProposalRepository()._apply(conn,'u',{'id':'p'},p)
    assert not any('update diet_strategies' in str(x) or 'insert into diet_strategies' in str(x)
                   for x in conn.execute.call_args_list)

async def test_agent_blocks_conflict_before_llm_validator_or_proposal(monkeypatch):
    from app.agents.team import DietTeam, StrategyDraft
    from app.agents.runtime import ToolFeedback
    from unittest.mock import AsyncMock
    p,u,c=fixture()
    c.append({**c[0],'id':'conflict','family':'other','low':1500,'high':1600})
    monkeypatch.setattr('app.rag.strategy_evidence.load_claims',lambda:c)
    team=DietTeam({'user_id':'u','message':'change targets'},repository=AsyncMock(),db=object())
    team.profile={**u,'strategy':None}; team.evidence={'e':p['evidence'][0]}
    team.validate=AsyncMock()
    args=StrategyDraft(**{k:p[k] for k in ('daily_calories','protein_g','carbs_g','fat_g')},
                       strategy_note='test',evidence_ids=['e'])
    with pytest.raises(ToolFeedback,match='evidence_policy_blocked'):
        await team.propose_strategy(args)
    team.validate.assert_not_called()
    assert team.proposal is None

async def test_agent_attaches_server_receipt_before_validator(monkeypatch):
    from app.agents.team import DietTeam, StrategyDraft
    from unittest.mock import AsyncMock
    p,u,c=fixture(); monkeypatch.setattr('app.rag.strategy_evidence.load_claims',lambda:c)
    c.append({**c[0], 'id':'secondary', 'family':'secondary', 'authority':'society_guideline',
              'low':1500, 'high':1600})
    team=DietTeam({'user_id':'u','message':'change targets'},repository=AsyncMock(),db=object())
    team.profile={**u,'strategy':None}; team.evidence={'e':p['evidence'][0]}; team.validate=AsyncMock()
    await team.propose_strategy(StrategyDraft(**{k:p[k] for k in ('daily_calories','protein_g','carbs_g','fat_g')},
                               strategy_note='test',evidence_ids=['e']))
    assert team.proposal['evidence_policy']['status']=='approved'
    assert team.validate.call_args.args[0]['evidence_policy']['decisions']
    assert 'secondary' in team.proposal['strategy_note']

async def test_catalog_change_after_proposal_blocks_approval(monkeypatch):
    from app.db.proposals import ProposalRepository, ProposalConflict
    from unittest.mock import AsyncMock
    p,u,c=fixture(); receipt=gate(p,u,c)
    p.update(kind='strategy',effective_date=service_today().isoformat(),based_on_strategy_id=None,
             strategy_note='test',policy_version=receipt['policy_version'],evidence_policy=receipt)
    c[0]['high']=2000  # still within bounds, but reviewed policy changed since confirmation card.
    monkeypatch.setattr('app.rag.strategy_evidence.load_claims',lambda:c)
    conn=AsyncMock(); conn.execute.return_value.fetchone.return_value=u
    with pytest.raises(ProposalConflict):
        await ProposalRepository()._apply(conn,'u',{'id':'p'},p)
    assert len(conn.execute.call_args_list)==1

async def test_repeated_setup_cannot_reset_active_strategy(fake_sb, mock_current_user):
    from app.api.routes.main import setup_user
    fake_sb.tables['users']=[{'id':mock_current_user}]
    fake_sb.tables['diet_strategies']=[{'daily_calories':1800,'protein_g':100,'carbs_g':230,
                                      'fat_g':53,'strategy_note':'approved'}]
    await setup_user('diet',170,70,30,'male',auth_id=mock_current_user)
    assert not any(table=='diet_strategies' for method,table,payload in fake_sb.calls)

async def test_unchanged_reviewed_policy_allows_strategy_apply(monkeypatch):
    from app.db.proposals import ProposalRepository
    from unittest.mock import AsyncMock
    p,u,c=fixture(); receipt=gate(p,u,c)
    p.update(kind='strategy',effective_date=service_today().isoformat(),based_on_strategy_id=None,
             strategy_note='test',policy_version=receipt['policy_version'],evidence_policy=receipt)
    monkeypatch.setattr('app.rag.strategy_evidence.load_claims',lambda:c)
    responses=[]
    for value in [u,None,None,{'id':'new-strategy'},None]:
        cursor=AsyncMock(); cursor.fetchone.return_value=value; responses.append(cursor)
    conn=AsyncMock(); conn.execute.side_effect=responses
    result=await ProposalRepository()._apply(conn,'u',{'id':'p'},p)
    assert result['strategy_id']=='new-strategy'
    assert 'strategy_versions' in conn.execute.call_args_list[-1].args[0]
