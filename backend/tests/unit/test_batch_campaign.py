"""Split submission and settlement with fake provider jobs only."""
import json,sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts/eval"))
from eval_budget import Budget,BudgetStop
import batch_agentic_judges as batches
import batch_campaign as campaign

@pytest.fixture(autouse=True)
def fixed_limits_for_split_scenarios(monkeypatch, request):
 if request.node.name == 'test_limits_unchanged_and_stopped_real_ledger_not_reopened':return
 import eval_budget
 # Keep split/denial scenarios independent of the approved campaign allocation.
 monkeypatch.setattr(eval_budget,'LIMITS',{'probe':.1,'development':.25,'comparison':3.,'judge':1.,'browser':.15})

def entry(i):
 return {"key":f"old|a{i}|baseline","kind":"single","attempt_id":f"a{i}","condition":"baseline",
         "payload":{"question":"q","gold":"g","answer":"saved answer","context":"saved evidence"}}

def completed(entries,missing=False,reverse=False):
 responses=[]
 for e in entries:
  usage=None if missing else NS(prompt_token_count=100,candidates_token_count=20,thoughts_token_count=5,cached_content_token_count=0)
  body=NS(text=json.dumps({"correct":True,"faithful":True,"reason":"supported"}),candidates=[],usage_metadata=usage)
  responses.append(NS(metadata={"key":e["key"]},response=body))
 if reverse:responses.reverse()
 return NS(state=NS(value="JOB_STATE_SUCCEEDED"),dest=NS(inlined_responses=responses))

def fake(monkeypatch):
 client=Mock()
 client.batches.create.return_value=NS(name="batches/one",state=NS(value="JOB_STATE_PENDING"))
 monkeypatch.setattr(batches,"batch_cost",lambda c,m,r:len(r)*.2)
 monkeypatch.setattr(batches,"requests_digest",lambda c,m,r:json.dumps(r,sort_keys=True))
 return client

def test_settlement_idempotent_and_usage_missing_never_refunds(tmp_path):
 b=Budget(tmp_path/"ledger.sqlite")
 t=b.reserve("judge",.4)
 b.bind_batch(t,"batches/one")
 assert not b.settle_batch(t,"batches/one",None,"missing")
 assert b.summary()["committed_usd"]==pytest.approx(.4)
 assert b.settle_batch(t,"batches/one",.02,"verified")
 assert b.settle_batch(t,"batches/one",.02,"verified")
 assert b.summary()["committed_usd"]==pytest.approx(.02)
 with pytest.raises(BudgetStop):b.settle_batch(t,"batches/other",.01,"verified")

def test_split_waits_then_settles_and_reuses_remaining_budget(tmp_path,monkeypatch):
 client=fake(monkeypatch);b=Budget(tmp_path/"ledger.sqlite")
 entries=[entry(i) for i in range(4)];requests=[{"i":i} for i in range(4)]
 path=tmp_path/"campaign.json"
 assert campaign.advance(client,path,"gemini-3.1-pro-preview",entries,requests,b,max_entries=2)=="pending"
 assert client.batches.create.call_count==1
 assert b.summary()["committed_usd"]==pytest.approx(.4)
 client.batches.get.return_value=NS(state=NS(value="JOB_STATE_RUNNING"),dest=None)
 assert campaign.advance(client,path,"gemini-3.1-pro-preview",entries,requests,b,max_entries=2)=="pending"
 assert client.batches.create.call_count==1
 client.batches.get.return_value=completed(entries[:2],reverse=True)
 client.batches.create.return_value=NS(name="batches/two",state=NS(value="JOB_STATE_PENDING"))
 assert campaign.advance(client,path,"gemini-3.1-pro-preview",entries,requests,b,max_entries=2)=="pending"
 assert client.batches.create.call_count==2
 assert b.summary()["committed_usd"]<.401
 client.batches.get.return_value=completed(entries[2:])
 assert campaign.advance(client,path,"gemini-3.1-pro-preview",entries,requests,b,max_entries=2)=="completed"
 assert client.batches.create.call_count==2
 assert b.summary()["committed_usd"]==pytest.approx(.001)
 # Already completed jobs are never submitted or charged again.
 assert campaign.advance(client,path,"gemini-3.1-pro-preview",entries,requests,b,max_entries=2)=="completed"
 assert client.batches.create.call_count==2

def test_unknown_create_outcome_cannot_resubmit_after_restart(tmp_path,monkeypatch):
 client=fake(monkeypatch);client.batches.create.side_effect=TimeoutError()
 b=Budget(tmp_path/"ledger.sqlite");path=tmp_path/"campaign.json"
 with pytest.raises(TimeoutError):campaign.advance(client,path,"gemini-3.1-pro-preview",[entry(0)],[{}],b)
 with pytest.raises(ValueError):campaign.advance(client,path,"gemini-3.1-pro-preview",[entry(0)],[{}],Budget(b.path))
 assert client.batches.create.call_count==1
 assert b.summary()["committed_usd"]==pytest.approx(.2)

def test_missing_usage_blocks_next_chunk(tmp_path,monkeypatch):
 client=fake(monkeypatch);b=Budget(tmp_path/"ledger.sqlite");path=tmp_path/"campaign.json"
 entries=[entry(0),entry(1)]
 campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=1)
 client.batches.get.return_value=completed(entries[:1],missing=True)
 assert campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=1)=="usage_unverified"
 assert client.batches.create.call_count==1
 assert b.summary()["committed_usd"]==pytest.approx(.2)

def test_budget_denial_and_input_drift_never_submit(tmp_path,monkeypatch):
 client=fake(monkeypatch);b=Budget(tmp_path/"ledger.sqlite");b.reserve("judge",.9)
 with pytest.raises(BudgetStop):campaign.advance(client,tmp_path/"campaign.json","gemini-3.1-pro-preview",[entry(0)],[{}],b)
 client.batches.create.assert_not_called()

def test_collect_crash_after_grades_write_can_still_settle(tmp_path,monkeypatch):
 client=fake(monkeypatch);b=Budget(tmp_path/"ledger.sqlite")
 path=tmp_path/"job.json";entries=[entry(0)]
 batches.submit_once(client,path,"gemini-3.1-pro-preview",[{}],entries,budget=b)
 client.batches.get.return_value=completed(entries)
 settle=b.settle_batch
 monkeypatch.setattr(b,"settle_batch",Mock(side_effect=RuntimeError("simulated crash before settlement")))
 with pytest.raises(RuntimeError):batches.collect(client,path,budget=b)
 preserved=path.with_suffix(".grades.jsonl").read_bytes()
 monkeypatch.setattr(b,"settle_batch",settle)
 result=batches.collect(client,path,budget=b)
 assert result["budget_settled"]
 assert path.with_suffix(".grades.jsonl").read_bytes()==preserved
 assert b.summary()["committed_usd"]<.001

def test_collection_only_never_submits_next_chunk(tmp_path,monkeypatch):
 client=fake(monkeypatch);b=Budget(tmp_path/"ledger.sqlite");path=tmp_path/"campaign.json"
 entries=[entry(0),entry(1)]
 campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=1)
 client.batches.get.return_value=completed(entries[:1])
 assert campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=1,submit_next=False)=="ready"
 assert client.batches.create.call_count==1

def test_conflicting_usage_duplicate_keys_and_lock_are_fail_closed(tmp_path,monkeypatch):
 client=fake(monkeypatch);b=Budget(tmp_path/"ledger.sqlite");path=tmp_path/"campaign.json"
 entries=[entry(0),entry(1)]
 campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=2)
 job=completed(entries);job.dest.inlined_responses[1].metadata={"key":entries[0]["key"]}
 client.batches.get.return_value=job
 with pytest.raises(ValueError,match="coverage"):
  campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=2)
 assert b.summary()["committed_usd"]==pytest.approx(.4)
 lock=path.with_suffix(".json.lock");lock.write_text("existing process")
 with pytest.raises(ValueError,match="locked"):
  campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=2)
 assert client.batches.create.call_count==1

def test_model_payload_and_ledger_changes_cannot_reuse_job(tmp_path,monkeypatch):
 client=fake(monkeypatch);b=Budget(tmp_path/"ledger.sqlite");path=tmp_path/"campaign.json"
 campaign.advance(client,path,"gemini-3.1-pro-preview",[entry(0)],[{}],b)
 changed=entry(0);changed["payload"]["answer"]="changed"
 with pytest.raises(ValueError,match="Frozen"):
  campaign.advance(client,path,"gemini-3.1-pro-preview",[changed],[{}],b)
 with pytest.raises(ValueError,match="Frozen"):
  campaign.advance(client,path,"gemini-3.1-pro-preview",[entry(0)],[{}],Budget(tmp_path/"other.sqlite"))
 assert client.batches.create.call_count==1

def test_smaller_final_chunk_and_cap_stop_without_extra_submission(tmp_path,monkeypatch):
 client=fake(monkeypatch);b=Budget(tmp_path/"ledger.sqlite");path=tmp_path/"campaign.json"
 b.reserve("judge",.7)
 entries=[entry(i) for i in range(4)]
 campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{}]*4,b,max_entries=4)
 assert len(client.batches.create.call_args.kwargs["src"])==1
 assert b.summary()["committed_usd"]==pytest.approx(.9)
 # Even a failed grade can be billable. Retain actual usage and refuse the next chunk.
 result=completed(entries[:1])
 result.dest.inlined_responses[0].response.usage_metadata=NS(prompt_token_count=100000,candidates_token_count=15000,thoughts_token_count=0,cached_content_token_count=0)
 client.batches.get.return_value=result
 with pytest.raises(BudgetStop):
  campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{}]*4,b,max_entries=4)
 assert client.batches.create.call_count==1
 assert b.summary()["stopped"]

def test_usage_settlement_conflict_does_not_release_twice(tmp_path):
 b=Budget(tmp_path/"ledger.sqlite");t=b.reserve("judge",.2);b.bind_batch(t,"batches/x")
 b.settle_batch(t,"batches/x",.1,"first")
 with pytest.raises(BudgetStop):b.settle_batch(t,"batches/x",.05,"second")
 assert b.summary()["committed_usd"]==pytest.approx(.1)

def test_real_sdk_batch_reserves_once_and_links_ticket(tmp_path,monkeypatch):
 from google import genai
 from google.genai._api_client import BaseApiClient
 from eval_budget import install_transport_guard
 calls=[]
 def transport(self,*args,**kwargs):
  calls.append(1)
  return NS(headers={},response_stream=[json.dumps({"name":"batches/sdk","metadata":{"state":"BATCH_STATE_PENDING"}})])
 monkeypatch.setattr(BaseApiClient,"_request",transport)
 for name in ["request","async_request","request_streamed","async_request_streamed"]:
  monkeypatch.setattr(BaseApiClient,name,getattr(BaseApiClient,name))
 b=Budget(tmp_path/"sdk.sqlite");install_transport_guard(b,"judge")
 client=genai.Client(api_key="offline-placeholder")
 entries=[entry(0)]
 requests=batches.make_requests(entries)
 cost=batches.batch_cost(client,"gemini-3.1-pro-preview",requests)
 batches.submit_once(client,tmp_path/"sdk.json","gemini-3.1-pro-preview",requests,entries,budget=b)
 assert len(calls)==1
 assert b.summary()["committed_usd"]==pytest.approx(cost,abs=0.000001)
 client.close()

def test_cached_input_not_discounted_twice():
 usage={"input_tokens":100,"output_tokens":25,"input_token_details":{"cache_read":40}}
 assert batches.batch_usage_cost("gemini-3.1-pro-preview",usage)==pytest.approx((60*1+40*.2+25*6)/1e6)

def test_100_saved_pairs_can_be_processed_in_chunks_without_100_pair_reservation(tmp_path,monkeypatch):
 client=fake(monkeypatch)
 # Deliberately high maximum reservation (.02 per entry) but tiny actual usage.
 monkeypatch.setattr(batches,"batch_cost",lambda c,m,r:len(r)*.02)
 b=Budget(tmp_path/"hundred.sqlite");path=tmp_path/"campaign.json"
 entries=[entry(i) for i in range(100)];requests=[{}]*100
 for n in range(11):
  client.batches.create.return_value=NS(name=f"batches/part{n}",state=NS(value="JOB_STATE_PENDING"))
  if n:client.batches.get.return_value=completed(entries[(n-1)*10:n*10])
  status=campaign.advance(client,path,"gemini-3.1-pro-preview",entries,requests,b,max_entries=10)
 assert status=="completed"
 assert client.batches.create.call_count==10
 assert b.summary()["committed_usd"]==pytest.approx(.025)
 rows=batches.read_rows(path.with_suffix(".grades.jsonl"))
 assert len(rows)==100
 # Functional simulation only, not a live cost/quality benchmark.

def test_saved_real_answers_request_build_is_offline_and_does_not_regenerate():
 root=Path(__file__).resolve().parents[3]
 directory=root/"docs/agentic_rag/20261021-budgeted-validation"
 cases=json.loads((directory/"cases.json").read_text(encoding="utf-8"))
 attempts=batches.read_rows(directory/"attempts.jsonl")
 entries=batches.pending_old_entries(cases,attempts,[])
 requests=batches.make_requests(entries)
 assert len(requests)==len(entries)==14
 assert all(e["payload"]["answer"]==next(r["answer"] for r in attempts if r["attempt_id"]==e["attempt_id"] and r["condition"]==e["condition"]) for e in entries)

def test_later_verified_usage_releases_hold_without_regrading(tmp_path,monkeypatch):
 client=fake(monkeypatch);b=Budget(tmp_path/"ledger.sqlite");path=tmp_path/"campaign.json"
 entries=[entry(0),entry(1)]
 campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=1)
 client.batches.get.return_value=completed(entries[:1],missing=True)
 assert campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=1)=="usage_unverified"
 client.batches.get.return_value=completed(entries[:1])
 client.batches.create.return_value=NS(name="batches/two",state=NS(value="JOB_STATE_PENDING"))
 assert campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=1)=="pending"
 rows=batches.read_rows(path.with_suffix(".parts")/"job-0000.grades.jsonl")
 assert rows[0]["cost_complete"]
 assert client.batches.create.call_count==2

def test_corrupt_saved_grade_prevents_advance_and_refund(tmp_path,monkeypatch):
 client=fake(monkeypatch);b=Budget(tmp_path/"ledger.sqlite");path=tmp_path/"campaign.json"
 entries=[entry(0),entry(1)]
 campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=1)
 (path.with_suffix(".parts")/"job-0000.grades.jsonl").write_text("corrupt")
 client.batches.get.return_value=completed(entries[:1])
 with pytest.raises(ValueError):
  campaign.advance(client,path,"gemini-3.1-pro-preview",entries,[{},{}],b,max_entries=1)
 assert client.batches.create.call_count==1
 assert b.summary()["committed_usd"]==pytest.approx(.2)

def test_limits_unchanged_and_stopped_real_ledger_not_reopened():
 import eval_budget
 assert eval_budget.TOTAL==5
 assert eval_budget.LIMITS=={"probe":.05,"development":.05,"comparison":2.6,"judge":2.2,"browser":.1}
 assert sum(eval_budget.LIMITS.values())==pytest.approx(5)

def test_concurrent_identical_settlement_refunds_only_once(tmp_path):
 from concurrent.futures import ThreadPoolExecutor
 b=Budget(tmp_path/"concurrent.sqlite");t=b.reserve("judge",.5);b.bind_batch(t,"batches/same")
 with ThreadPoolExecutor(max_workers=8) as pool:
  assert all(pool.map(lambda _:Budget(b.path).settle_batch(t,"batches/same",.01,"same-usage"),range(16)))
 assert b.summary()["committed_usd"]==pytest.approx(.01)
