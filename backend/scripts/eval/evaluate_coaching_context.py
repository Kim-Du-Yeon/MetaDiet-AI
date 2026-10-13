"""Deterministic call/query-count experiment, not a live latency benchmark."""
import asyncio,json,sys,subprocess,types
from pathlib import Path
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.agents.team import DietTeam,Empty
ROOT=Path(__file__).resolve().parents[3]
class Model:
    def __init__(self,responses):self.ainvoke=AsyncMock(side_effect=responses)
    def bind_tools(self,schemas):return self
def call(name,args):return AIMessage(content='',tool_calls=[{'name':name,'args':args,'id':name,'type':'tool_call'}])
async def main():
    source=subprocess.check_output(['git','show','b25d0b7:backend/app/agents/team.py'],cwd=ROOT,timeout=30).decode('utf-8')
    old=types.ModuleType('coaching_baseline');sys.modules[old.__name__]=old;exec(compile(source,'<baseline>','exec'),old.__dict__)
    rows=[]
    for label,cls in [('before',old.DietTeam),('after',DietTeam)]:
        team=cls({'user_id':'fixture','message':'점심 추천해줘','requested_action':'meal_plan'},repository=AsyncMock(),db=object())
        async def read(table,**filters):return [{'goal':'diet'}] if table=='users' else [{'daily_calories':2000}] if table=='diet_strategies' else [{'calories':300}]
        team.rows=AsyncMock(side_effect=read)
        for _ in range(2):await team.read_profile(Empty());await team.read_intake(Empty())
        queries=team.rows.await_count
        root=Model([call('delegate_meal',{'query':'점심 조언'})])
        child=Model(([AIMessage(content='',tool_calls=[{'name':'read_profile','args':{},'id':'p','type':'tool_call'},{'name':'read_intake','args':{},'id':'i','type':'tool_call'}])] if label=='before' else [])+[AIMessage(content='담백한 식사를 선택하세요.')])
        models=iter([root,child]);team=cls({'user_id':'fixture','message':'점심 추천해줘','requested_action':'meal_plan'},model_factory=lambda:next(models),repository=AsyncMock(),db=object())
        team.rows=AsyncMock(side_effect=read);result=await team.execute()
        rows.append({'phase':label,'repeated_read_db_queries':queries,'coaching_model_calls':result['execution_usage']['model_calls'],
            'coaching_tool_budget':result['execution_usage']['tool_calls'],'coaching_db_queries':team.rows.await_count})
    assert rows[0]['repeated_read_db_queries']==6 and rows[1]['repeated_read_db_queries']==3
    assert rows[0]['coaching_model_calls']==3 and rows[1]['coaching_model_calls']==2
    report={'baseline':'b25d0b7','scope':'synthetic_scripted_model_query_counts','rows':rows,
        'limitations':'Scripted model paths demonstrate removed round trip, not guaranteed live model behavior. One ordinary request still needs 3 fresh DB reads.'}
    (ROOT/'docs/coaching_performance/CONTROLLED.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
