"""Frozen separate development comparison for optional closing offers; not independent validation."""
import copy,hashlib
from pathlib import Path
from scripts.eval.clarification_holdout import ROOT,cases as old_cases
from scripts.eval.clarification_v3 import read,sha
from scripts.eval.clarification_cases import validate_cases,can_reuse
from scripts.eval.clarification_execution import CONDITIONS,request_spec
from app.core.prompt_release_control import digest,_snapshot
BASE=ROOT/'docs/prompt_control/clarification-balanced/v4-approval-policy-v2-20261022'
FOLDER=BASE.parent/'v5-closing-offer-20261022'
SUITE='clarification-closing-offer-v5'
CLOSING_RULE="""답변의 종료 규칙을 지키세요.
현재 질문에 필요한 답을 제공했으면 그 답으로 끝내세요. 사용자가 요청하지 않은 다음 상담·식사 기록·식단 추천을 유도하는 선택적 마무리 제안도 불필요한 후속 요청입니다. 물음표가 없어도 '필요하시면 말씀해 주세요', '원하시면 더 도와드릴게요', '추가 기록이나 추천이 필요하면 알려주세요' 같은 종결문을 덧붙이지 마세요.
필수 정보 질문은 유지하세요. 먹은 분량·개별 레시피 재료와 양·제품 식별 또는 영양표·누락된 선택지나 지시 대상이 없어서 요청한 결과를 확정할 수 없으면, 그 누락 정보만 짧게 직접 물으세요. 이를 임의 값이나 일반 안내로 대체하지 마세요. 이미 제공된 값은 다시 묻지 마세요.
사용자가 다음 단계나 구체적인 실천 방법을 명시적으로 요청했다면 그 내용을 답변에 포함하세요. 안전상 필요한 주의·전문가 상담 안내도 유지하세요. 답변 뒤의 불필요한 재방문·추가 입력 유도와 현재 요청에 답하기 위한 필수 질문·안내를 구분하세요."""


def cases():
    source=old_cases();out=[]
    for c in sorted(source,key=lambda x:(x['family']!='stale',x['family'],x['id'])):
        c=copy.deepcopy(c);family=c['family'];i=int(c['id'].split('-')[-1]);c.update(id=f'v5-{family}-{i:02d}',split='development',provenance='Separate synthetic development, one known regression replay +99 new question strings; not independent holdout')
        if family=='stale' and i==0:
            c=copy.deepcopy(next(x for x in source if x['id']=='h5-stale-06'));c.update(id='v5-stale-00',split='development',provenance='Known optional-offer regression replay; saved baseline reused by exact request identity')
        else:
            v=c['verified_context'];v.update(calories=529+i*43,target=2071+i*29)
            if family=='stale':c['question']=f"합계가 정정되어 현재 확정 섭취는 {v['calories']}kcal, 기준 목표는 {v['target']}kcal입니다. 옛 대화 수치는 제외하고 현재 남은 열량을 계산해주세요."
            elif family=='updated_goal':c['question']=f"새로 저장한 목표 {v['target']}kcal와 현재 합계 {v['calories']}kcal로 오늘 남은 열량을 구해주세요. 이전 목표는 유효하지 않아요."
            elif family=='known_reference':
                rate=143+i*7;grams=117+i*11;v['nutrition_reference']={'per_100g_kcal':rate,'consumed_g':grams};c['question']=f"제공된 영양표는100g당 {rate}kcal이고 양은{grams}g이에요. 표 기준으로 열량만 환산해주세요."
            elif family=='ordinary':c['question']=['그럼 일반식 먹어도 괜찮나요?','그러면 샌드위치 먹어도 돼?','점심에 계란 먹는 건 괜찮아?','그럼 닭가슴살 먹어도 될까?','아침에 밥 먹어도 괜찮나요?','그러면 샐러드 먹어도 괜찮을까?','저녁에 일반식 먹어도 돼?','그럼 밥이랑 계란 먹어도 될까?','점심에 한식뷔페 한 접시 먹어도 괜찮나요?','아침에 샌드위치 먹어도 될까?'][i]
            elif family=='unlogged':c['question']=f"오늘 저녁은 모임 {i+1}에서 일반식 예정이고 아직 먹지 않았어요. 점심을 굶지 않고 준비할 실천 방법 두 가지와 다음 행동을 알려주세요."
            elif family=='portion':c['question']=f"표준 성분표로 음식 {i+1}번의 열량을 환산하려는데 실제 먹은 양만 아직 없어요. 기본 분량 추정은 원치 않습니다. 무엇을 확인해야 하나요?"
            elif family=='recipe':c['question']=f"직접 만든 채소콩조림 {125+i*12}g의 레시피별 열량을 계산하고 싶어요. 대표 성분표 대신 내 재료별 양, 기름과 양념, 완성 총량을 반영할 건데 이 값들은 아직 안 드렸어요. 필요한 것을 물어봐주세요."
            elif family=='label':c['question']=f"포장 간식 {i+51}번의 정확한 당류를 확인하려고요. 제품명과 영양표는 아직 없으니 다른 제품을 가정하지 말고 필요한 정보를 확인해주세요."
            elif family=='choices':c['question']=f"후보 메뉴 {i+61}와 {i+62} 중 하나만 골라주세요. 두 이름은 현재 대화에 빠져 있어요."
            else:c['question']=f"제가 말한 {i+71}번 음식을 점심에 먹어도 괜찮나요? 음식 이름과 설명은 이 대화에 없습니다."
        out.append(c)
    validate_cases(out);return out


def candidate_snapshot(base):
    s=copy.deepcopy(base);s.update(kind='evaluation',origin_commit=None);s.pop('signature',None);s['manifest'].pop('validation',None);s['manifest']['release']='clarification-v5-20261022'
    for n in ['team.base','team.compact_followup']:
        s['texts'][n]+='\n'+CLOSING_RULE;h=hashlib.sha256(s['texts'][n].encode()).hexdigest();s['manifest']['prompts'][n].update(sha256=h,commit=h)
    _snapshot(s);return s


def reuse_regression(case,snapshot):
    r=copy.deepcopy(next(x for x in read(BASE/'staging-smoke.json')['rows'] if x['case_id']=='h5-stale-06'))
    if not can_reuse(r,case,request_spec(snapshot)):raise ValueError('Saved regression input/prompt/settings mismatch')
    r.update(case_id=case['id'],condition='v4',reused_from='v4-approval-policy-v2-20261022/staging-smoke.json#h5-stale-06')
    return r


def select(values):
    a,b=values['v4'],values['v5'];checks={
        'complete_candidate':b['expected']==b['judged']==100 and b['generation_failures']==0 and b['usage_complete'],
        'baseline100_accounted':a['expected']==a['attempted']==100 and a['usage_complete'],
        'quality':all(b[k]>=98 and b[k]>=a[k]-1 for k in ['correct','faithful']),
        'behavior':b['passed']>=max(98,a['passed']),
        'required50':b['required_recall_numerator']==50,
        'unsafe0':b['unsafe_commitments']==0,
        'fresh_no_write100':b['fresh']==b['no_write']==100,
        'closing_reduced':b['unnecessary_all']<=2 and b['unnecessary_all']<a['unnecessary_all'],
        'p95_cost':b['p95_ms']<=a['p95_ms']*1.25 and b['cost_usd']<=a['cost_usd']*1.25}
    return {'candidate_passed':all(checks.values()),'checks':checks,'scope':'Known regression plus99 new separate synthetic development cases; not independent holdout/users','production_adoption':False}


def code_sha():
    names=['backend/scripts/eval/clarification_v5.py','backend/scripts/eval/run_clarification_v5.py','backend/scripts/eval/approve_clarification_v5.py','backend/scripts/prompt_release_workflow.py']
    names+=list(read(BASE.parent/'v4-independent-20261022/protocol.json')['code_sha256'])
    return {n:hashlib.sha256((ROOT/n).read_text(encoding='utf-8-sig').encode()).hexdigest() for n in dict.fromkeys(names)}


def validate(folder):
    p=read(Path(folder)/'protocol.json')
    if p['code_sha256']!=code_sha() or p['cases_sha256']!=digest(read(Path(folder)/'frozen.json')) or p['candidate_sha256']!=digest(read(Path(folder)/'candidate.json')):raise ValueError('Frozen v5 protocol changed')
    for n,h in p['source_hashes'].items():
        if sha(BASE/n)!=h:raise ValueError('Historical v4 evidence changed')
    return p
