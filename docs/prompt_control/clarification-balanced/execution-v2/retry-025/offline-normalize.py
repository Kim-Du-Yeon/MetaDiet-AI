"""Lossless reparse of saved raw grades; no provider transport or budget mutation."""
import hashlib,json,socket,sys
from pathlib import Path
from unittest.mock import patch
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'backend/app').exists())
sys.path.insert(0,str(ROOT/'backend'))
from scripts.eval.batch_clarification_resume import parse_grade
from scripts.eval.clarification_execution import digest
from scripts.eval.cache_artifacts import save_json
from scripts.eval.run_clarification_comparison import summarize_folder
folder=Path(__file__).resolve().parent
out=folder/'post-batch-normalization.json'
if out.exists():raise SystemExit('Already recorded; do not overwrite previous evidence')
with patch.object(socket,'create_connection',side_effect=AssertionError('Offline only')):
 data=json.loads((folder/'judges.json').read_text(encoding='utf-8'))
 before=json.loads(json.dumps(data));changes=[]
 history=json.loads((folder/'parse-history.json').read_text(encoding='utf-8'))
 for row in data['rows']:
  if row['status']=='completed':continue
  raw=json.loads((folder/'raw-grades'/(row['case_id']+'.json')).read_text(encoding='utf-8'))
  assert digest(raw)==row['raw_sha256']
  assert raw['usage']==row['usage'][0] and raw['finish_reasons']==['FinishReason.STOP']
  try:grades=parse_grade(raw['text']).model_dump()
  except ValueError:continue
  prior=json.loads(json.dumps(row));row.pop('error');row.update(status='completed',grades=grades)
  history.append({'prior':prior,'replacement_sha256':digest(row),'reason':'Complete named fields only; offline normalization, no new model call'})
  changes.append({'case_id':row['case_id'],'raw_sha256':row['raw_sha256'],'grades':grades,'usage_unchanged':True,'answer_binding_unchanged':True})
 assert len(changes)==3
 by={r['case_id']:r for r in data['rows']}
 assert all(by[r['case_id']]==r for r in before['rows'] if r['status']=='completed')
 save_json(folder/'pre-final-normalization-judges.json',before)
 save_json(folder/'judges.json',data);save_json(folder/'parse-history.json',history)
 save_json(out,{'recovered_pairs':3,'new_model_calls':0,'cost_change_usd':0,'all_prior_completed_preserved':True,'parser_module_sha256':hashlib.sha256((ROOT/'backend/scripts/eval/batch_clarification_resume.py').read_bytes()).hexdigest(),'changes':changes})
 summarize_folder(folder)
 print(json.dumps({'recovered_pairs':3,'new_model_calls':0}))
