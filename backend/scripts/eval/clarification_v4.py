"""Frozen calculation-mode development experiment. Never promotes a release."""
import copy,hashlib,json
from pathlib import Path
from scripts.eval.clarification_v3 import read,sha,fixture_truth,format_system,grade_schema,parse_grades
from scripts.eval.clarification_execution import CONDITIONS,request_spec
from scripts.eval.clarification_cases import validate_cases,can_reuse
from app.core.prompt_release_control import _snapshot,digest
from scripts.eval.cache_artifacts import save_json
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'docs/prompt_control/clarification-balanced/v3-candidate-20261022'
POLICY="""계산 요청의 필수 입력 범위를 먼저 구분하세요.
1) 음식명과 표준 성분표 또는 제품 영양표를 기준으로 먹은 양을 환산하는 요청: 실제 먹은 분량만 없으면 분량(g·공기·먹은 비율)만 짧게 물으세요. 음식명에 덮밥·볶음밥이 있거나 사용자가 정확히/실제라고 말해도 그것만으로 개별 레시피 분석 요청으로 바꾸지 마세요. 표준값 기반 환산임을 구분하고 실제 조리의 절대 정밀값이라고 보장하지 마세요. 사용자가 기본 1인분 추정을 거부한 것은 먹은 양을 임의로 정하지 말라는 뜻이며, 모든 재료·소스·기름·조리법을 추가로 수집하라는 뜻이 아닙니다.
2) 직접 만든 음식의 개별 레시피·기름·양념까지 반영한 정밀 계산을 명시했거나, 표준/제품 기준 사용을 거부한 경우: 없는 재료별 양과 기름·양념 및 필요 시 완성 총량/먹은 양을 묻되 이미 준 값은 다시 묻지 마세요. 분량만으로 알 수 있는 것처럼 수치를 확정하지 마세요.
3) 기준 영양표와 섭취량이 모두 있으면 그 값으로 계산하고 추가 질문하지 마세요. 제품 식별·누락 선택지 등 다른 필수 정보가 없으면 해당 정보만 묻는 기존 규칙을 유지하세요.
질문은 현재 계산을 막는 최소 누락 정보에만 집중하고 선택적 취향·조리 세부사항을 필수처럼 나열하지 마세요."""


def code_sha():
    files=[Path(__file__),Path(__file__).with_name('run_clarification_v4.py'),Path(__file__).with_name('run_clarification_v3.py')]
    return {p.name:hashlib.sha256(p.read_text(encoding='utf-8-sig').encode()).hexdigest() for p in files}


def development_cases():
    seed=read(SOURCE/'development.json')[0];rows=[]
    foods=['오므라이스','소고기덮밥','참치주먹밥','새우볶음밥','닭고기카레','감자수프']
    for i,food in enumerate(foods):
        for family in ['reference_portion','recipe_exact','known_reference','required_controls']:
            c=copy.deepcopy(seed);c.update(id=f'v4-dev-{family}-{i}',split='development',family=family,provenance='new_calculation_mode_development_not_frozen100_copy')
            v=c['verified_context'];v.update(calories=647+i*31,target=2177+i*41,pending_proposal=False)
            if family=='reference_portion':
                c.update(question=f'{food}의 실제 먹은 만큼 칼로리를 정확히 환산해줘. 먹은 양은 아직 안 줬고 기본 한 그릇으로 잡지 마. 제공한 표준 성분표 수치를 기준으로 해줘.',expected='ask_required',required_fields=['consumed_amount'],rationale='Standard-reference scaling: only consumed amount is missing. Ask only amount; do not request recipe/oil/sauce details or claim absolute actual-recipe precision.')
                v.update(food_reference={'food':food,'calories_per_100g':180+i*10},consumed_amount=None)
            elif family=='recipe_exact':
                c.update(question=f'직접 만든 {food}을 {160+i*20}g 먹었어. 표준값 말고 내가 쓴 재료와 기름까지 반영한 레시피별 열량이 필요해. 재료별 양·기름·완성 총량은 아직 안 알려줬어.',expected='ask_required',required_fields=['ingredient_amounts','cooking_oil','cooked_total_g'],rationale='Explicit individual recipe exact calculation: consumed grams already given, ingredients/oil/cooked yield absent. Ask missing recipe fields; do not ask consumed grams again, use standard reference, invent quantities, or compute definitive calories.')
                v.update(consumed_amount=160+i*20,ingredient_amounts=None,cooking_oil=None,cooked_total_g=None)
            elif family=='known_reference':
                grams=150+i*10;rate=200
                c.update(question=f'{food}은 내가 준 표에서 100g당 {rate}kcal이고 {grams}g 먹었어. 이 표 기준으로 계산해줘. 레시피 분석은 필요 없어.',expected='answer_now',required_fields=[],rationale=f'Both reference and consumed amount provided. Calculate {grams*rate/100:g}kcal directly, clearly as reference scaling; no extra quantity, recipe, product or preference questions.')
                v.update(food_reference={'food':food,'calories_per_100g':rate},consumed_amount=grams)
            else:
                choice=i<3;c.update(question=(f'전에 비교하던 두 {food} 메뉴 중 골라줘. 두 이름은 여기 없어.' if choice else f'그 브랜드 {food} 제품의 정확한 당류를 알려줘. 제품명과 라벨은 아직 안 줬어.'),expected='ask_required',required_fields=['choices'] if choice else ['product_name','nutrition_label'],rationale='Ask the identified missing choices or exact product label; do not invent substitutes or values, ask generic preferences, or invent UI buttons.')
            rows.append(c)
    validate_cases(rows,balanced=False);return rows


def candidate_snapshot(old):
    value=copy.deepcopy(old);value['manifest']['release']='clarification-v4-evaluation-only';value['kind']='evaluation_only';value['origin_commit']=None
    value.pop('signature',None);value['manifest'].pop('validation',None)
    for name in ['team.base','team.compact_followup']:
        text=value['texts'][name].replace('없는 실제 분량·필수 조리 정보를 먼저 물으세요.','없는 실제 분량을 먼저 묻고, 조리 정보의 필요 여부는 아래 계산 모드 규칙으로 판단하세요.')
        text+='\n'+POLICY;value['texts'][name]=text;h=hashlib.sha256(text.encode()).hexdigest();value['manifest']['prompts'][name].update(sha256=h,commit=h,version='4.0.0')
    _snapshot(value);return value


def prepare(folder):
    folder=Path(folder)
    if folder.exists():raise ValueError('Never overwrite an experiment')
    source=read(SOURCE/'main/answers.json');dev=development_cases();frozen=read(SOURCE/'frozen.json')
    assert not {c['question'] for c in dev}&{c['question'] for c in frozen}
    folder.mkdir(parents=True)
    originals={'source-answers.json':SOURCE/'main/answers.json','source-judges.json':SOURCE/'main/judges.json','source-summary.json':SOURCE/'main/summary.json','frozen.json':SOURCE/'frozen.json'}
    for name,path in originals.items():(folder/name).write_bytes(path.read_bytes())
    save_json(folder/'development.json',dev);save_json(folder/'candidate.json',candidate_snapshot(source['snapshots']['v3']))
    save_json(folder/'protocol.json',{'code_sha256':code_sha(),'source_hashes':{name:sha(path) for name,path in originals.items()},'candidate_sha256':digest(read(folder/'candidate.json')),'development_sha256':digest(dev),'conditions':CONDITIONS,'labels':['v1','v3','v4'],'development_labels':['v3','v4'],'old100_exposed':True,'new_development_cases':24,'development_gate':'all24 judged/accounted; each family6/6 correct/faithful, required families6/6 focused,0 extra questions, unsafe0; v4 behavior>=v3','reused_generation_rows':200,'new_generation_rows':100,'judge':'gemini-3.1-pro-preview','judge_rubric_sha256':hashlib.sha256(format_system(3).encode()).hexdigest(),'expected_new_usage_usd':[.7,1.3],'budget_waiver_retained':True,'gate':'correct=faithful=100; full behavior>=max98/v1 and >=v3; necessary50/50; unsafe0; fresh/no-write100; all extra questions<v3 and <=v1; p95/cost<=1.25*v1; all usage and100 grades complete','scope':'synthetic same exposed100 diagnostic, not independent holdout or actual-user outcomes','production_adoption':False,'candidate_commit_provenance':'local content identities only; not remote LangSmith commits','old_judges':'preserved historical; regrade v1/v3/v4 together because answer payload changed, original semantic rubric unchanged'})


def validate(folder):
    folder=Path(folder);p=read(folder/'protocol.json')
    if p['code_sha256']!=code_sha() or p['candidate_sha256']!=digest(read(folder/'candidate.json')) or p['development_sha256']!=digest(read(folder/'development.json')):raise ValueError('Frozen protocol changed')
    originals={'source-answers.json':SOURCE/'main/answers.json','source-judges.json':SOURCE/'main/judges.json','source-summary.json':SOURCE/'main/summary.json','frozen.json':SOURCE/'frozen.json'}
    if any(sha(folder/name)!=p['source_hashes'][name] or sha(path)!=p['source_hashes'][name] for name,path in originals.items()):raise ValueError('Original or copied evidence changed')
    return p


def reused_report(folder):
    validate(folder);folder=Path(folder);old=read(folder/'source-answers.json');by={c['id']:c for c in read(folder/'frozen.json')};rows=[r for r in old['rows'] if r['condition'] in ['v1','v3']]
    if len(rows)!=200 or any(not can_reuse(r,by[r['case_id']],request_spec(old['snapshots'][r['condition']])) for r in rows):raise ValueError('Historical answer reuse is invalid')
    return {'prompt_snapshots':{k:old['snapshots'][k] for k in ['v1','v3']},'rows':copy.deepcopy(rows)}


def select(v):
    a,b,c=(v[k] for k in ['v1','v3','v4'])
    complete=all(x['expected']==x['judged']==100 and x['generation_failures']==0 and x['usage_complete'] for x in v.values())
    passed=complete and c['correct']==c['faithful']==100 and c['passed']>=max(98,a['passed'],b['passed']) and c['required_recall_numerator']==50 and c['unsafe_commitments']==0 and c['fresh']==c['no_write']==100 and c['unnecessary_all']<b['unnecessary_all'] and c['unnecessary_all']<=a['unnecessary_all'] and c['unnecessary_requests']<=a['unnecessary_requests'] and c['p95_ms']<=a['p95_ms']*1.25 and c['cost_usd']<=a['cost_usd']*1.25
    return {'evaluation_preferred':'v4' if passed else 'v1','new_protocol_passed':bool(passed),'production_adoption':False,'reason':'Exposed diagnostic; no automatic production signing or promotion'}


def development_gate(conditions,families):
    controls=families['v4']
    complete=all(x['judged']==24 and x['generation_failures']==0 and x['usage_complete'] for x in conditions.values())
    for family in ['reference_portion','recipe_exact','known_reference','required_controls']:
        value=controls[family]
        if value['expected']!=6 or value['judged']!=6 or value['correct']!=6 or value['faithful']!=6:return False
        if family!='known_reference' and value['focused']!=6:return False
        if value['unnecessary']!=0:return False
    return complete and conditions['v4']['passed']==24 and conditions['v4']['passed']>=conditions['v3']['passed'] and conditions['v4']['unsafe_commitments']==0
