"""Isolate SSE delivery with identical completed answers and no model/network."""
import asyncio,json,subprocess,statistics,sys,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.api.routes import main as current
ROOT=Path(__file__).resolve().parents[3]
async def main():
 source=subprocess.check_output(['git','show','cc30a62:backend/app/api/routes/main.py'],cwd=ROOT,timeout=30).decode('utf-8')
 namespace={'asyncio':asyncio,'_sse':current._sse,'_sv':current._sv,'_public_stats':AsyncMock(return_value={})}
 exec(compile(source[source.index('async def _stream('):source.index('async def _public_stats(')],'<baseline-stream>','exec'),namespace)
 stats=current._public_stats;current._public_stats=AsyncMock(return_value={});rows=[]
 try:
  for size in [20,100,200]:
   text=' '.join(['고정답변']*size)
   graph=SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={'response':text},next=())))
   for phase,stream in [('before',namespace['_stream']),('after',current._stream)]:
    samples=[]
    for _ in range(3):
     start=time.perf_counter();frames=[f async for f in stream(graph,{'configurable':{'thread_id':'u_t'}},'r')];samples.append(round((time.perf_counter()-start)*1000,3))
     events=[json.loads(f.split('data: ',1)[1]) for f in frames]
     assert ''.join(e['content'] for e in events if e['type']=='answer_delta')==text+' '
     assert [e['seq'] for e in events[:-1]]==list(range(1001,1001+size))
     assert events[-1]['type']=='completed'
    rows.append({'words':size,'phase':phase,'samples_ms':samples,'median_ms':statistics.median(samples)})
 finally:current._public_stats=stats
 report={'scope':'isolated_completed_answer_delivery_no_model_no_network','baseline':'cc30a62','rows':rows,'limitations':'Local loop timings are not public API latency. Identical answers isolate artificial pacing.'}
 (ROOT/'docs/answer_delivery/CONTROLLED_DELIVERY.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':asyncio.run(main())
