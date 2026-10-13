"""20 scenarios x 5 repetitions: real team context flow, scripted models/fake DB."""
import json
from datetime import date
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage
import pytest
from app.agents.team import DietTeam
MODES=['confirmed','revised','deleted','other_thread','goal_changed','new_day','other_user','read_failed','same_request_repeat','cancelled']
CASES=[(f'{mode}-{meal}',mode,meal) for mode in MODES for meal in ['점심','저녁']]
@pytest.mark.parametrize('repeat',range(5))
@pytest.mark.parametrize('name,mode,meal',CASES)
@pytest.mark.parametrize('direct_followup',[False, True, 'first'])
async def test_multiturn_latest_context_and_no_unconfirmed_writes(monkeypatch,name,mode,meal,repeat,direct_followup):
 day=[date(2026,10,13)];monkeypatch.setattr('app.agents.team.service_today',lambda:day[0])
 from app.core.config import get_settings
 monkeypatch.setattr(get_settings(),'first_coaching_mode','low' if direct_followup=='first' else 'off')
 db={'calories':300,'target':2000};captured=[]
 class Model:
  def bind_tools(self,schemas):return self
  async def ainvoke(self,messages,config=None):
   request=json.loads(messages[-1].content);captured.append(request)
   return AIMessage(content='합성 코칭 응답')
 async def rows(table,**filters):
  if table=='users':return [{'goal':'diet'}]
  if table=='diet_strategies':return [{'daily_calories':db['target']}]
  assert filters['user_id']==user[0] and filters['log_date']==day[0].isoformat()
  return [] if db['calories']==0 else [{'calories':db['calories']}]
 user=['u1'];repo=AsyncMock();history=[]
 async def turn(thread):
  followup = direct_followup and bool(history)
  first_advice = direct_followup=='first'
  team=DietTeam({'user_id':user[0],'message':meal+' 추천해줘. 조언만 해줘.' if first_advice else ('그럼 한식뷔페 먹어도 괜찮아?' if followup else meal+' 추천해줘'),'messages':history,'requested_action':None if followup or first_advice else 'meal_plan','thread_id':thread},repository=repo,db=object(),model_factory=Model)
  team.rows=AsyncMock(side_effect=rows)
  result=await team.execute()
  return team,result
 first,_=await turn('t');history += [{'role':'user','content':meal+' 추천해줘'},{'role':'assistant','content':'이전 기록은 300kcal였어요.'}]
 if mode in ['confirmed','revised','other_thread']:db['calories']=600+repeat
 elif mode=='deleted':db['calories']=0
 elif mode=='goal_changed':db['target']=1800
 elif mode=='new_day':day[0]=date(2026,10,14);db['calories']=0
 elif mode=='other_user':user[0]='u2';db['calories']=100
 original_rows=rows
 if mode=='read_failed':
  async def rows(*args,**kwargs):raise ConnectionError('synthetic unavailable')
 second,result=await turn('other' if mode=='other_thread' else 't')
 assert result['agent_used'] == ('meal' if direct_followup and mode!='read_failed' else 'supervisor')
 ctx=captured[-1]['verified_context']
 assert captured[-1]['recent_messages']
 if mode=='read_failed':
  assert ctx['status']=='unavailable' and 'intake' not in ctx
 else:
  assert ctx['intake']['calories']==db['calories']
  assert ctx['intake']['date']==day[0].isoformat()
  assert ctx['profile']['strategy']['daily_calories']==db['target']
 if mode=='same_request_repeat':
  from app.agents.team import Empty
  count=second.rows.await_count
  await second.read_intake(Empty());await second.read_profile(Empty())
  assert second.rows.await_count==count
 repo.create.assert_not_called();repo.resolve.assert_not_called()
