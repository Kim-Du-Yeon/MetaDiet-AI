"""Prospectively frozen v4 holdout and reviewed two-template approval boundary."""
import copy,hashlib,json,math
from pathlib import Path
from app.core.prompt_release_control import digest
from scripts.eval.clarification_cases import validate_cases
from scripts.eval.clarification_execution import CONDITIONS
from scripts.eval.clarification_v3 import read,sha
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'docs/prompt_control/clarification-balanced/v4-calculation-mode-20261022'
SUITE='clarification-two-template-holdout-v1'
COHORT_SHA='2b6a6fad2c5061f63c2c812474cf18eda371c0112fef6107159642d88c9e52c5'
GATE='100 completed/judged/accounted each; candidate correct and faithful>=98 and >=baseline-1, behavior>=98 and >=baseline, required>=49/50, unsafe0, fresh/no-write100, extra<=2 and <=baseline, p95/cost<=1.25baseline; old diagnostic gate also required'


def cases():
    portions=['콩나물국밥','메밀국수','참치비빔밥','새우죽','감자수프','잡곡김밥','버섯리소토','토마토파스타','연어덮밥','잔치국수']
    recipes=['렌틸콩스튜','해물찜','닭감자조림','두부강정','가지그라탱','볶음쌀국수','콩비지전','고등어조림','토마토달걀볶음','채소카레']
    ordinary=['회사 구내식당 백반','편의점 주먹밥과 우유','칼국수와 달걀','생선구이 정식','두부김치와 밥','보리밥 정식','새우 샌드위치','순두부와 잡곡밥','구운 감자와 요거트','닭안심 샐러드']
    out=[]
    for family in ['portion','recipe','known_reference','label','choices','referent','ordinary','updated_goal','stale','unlogged']:
        for i in range(10):
            amount=115+i*13;ref=135+i*9;v={'scope':'fresh_current_request','calories':487+i*41,'target':1943+i*31,'record_completeness':'unknown','pending_proposal':False}
            hist=[{'role':'user','content':'점심 메뉴 추천 부탁해요.'},{'role':'assistant','content':'현재 목표를 참고해 일반적인 식사 선택을 도와드릴게요.'}]
            fields=[];expected='answer_now'
            if family=='portion':
                q=f'{portions[i]} 먹은 열량을 성분표 기준으로 환산하려고요. 몇 g 먹었는지는 아직 안 적었고 평균 1인분을 대신 넣지는 말아주세요. 무엇이 더 필요한가요?'
                v['nutrition_reference']='표준 성분표 대표값 사용 동의; 섭취량 미제공';fields=['consumed_amount']
            elif family=='recipe':
                q=f'직접 만든 {recipes[i]} {amount}g을 먹었어요. 평균 성분표 말고 내 조리법대로 계산할래요. 들어간 재료와 각각의 양, 기름·양념, 완성 총량은 아직 안 알려드렸어요. 어떤 정보를 드려야 하나요?'
                fields=['ingredient_amounts','oil_seasoning','cooked_yield']
            elif family=='known_reference':
                q=f'포장 식품 영양표에 100g당 {ref}kcal라고 적혀 있고 {amount}g 먹었어요. 곁들인 것은 없어요. 열량만 계산해 주세요.'
                v['nutrition_reference']={'per_100g_kcal':ref,'consumed_g':amount}
            elif family=='label':
                q=f'마트에서 산 간식 번호 {i+21}의 실제 당류를 알고 싶어요. {amount}g 먹었지만 이름과 영양표는 아직 없어요. 임의 제품으로 대신하지 말고 확인해줘요.'
                fields=['product_identity_or_label']
            elif family=='choices':
                q=f'주문 후보 {i+31}번과 {i+32}번 중 다이어트 점심으로 하나 골라주세요. 이 대화에는 두 메뉴 이름이 아직 없어요.'
                fields=['choices']
            elif family=='referent':
                q=f'어제 이야기했던 {i+41}번 메뉴를 오늘도 먹어도 되나요? 그 메뉴 이름은 지금 대화에서 빠졌고 오늘 상황은 달라졌어요.'
                fields=['referent']
            elif family=='ordinary':q=['점심에 일반식 먹는 건 괜찮아?','저녁에 밥 먹는 건 그런가?','그러면 계란 먹는 건 괜찮아?','그럼 샐러드 먹는 건 그런가?','아침에 샌드위치 먹는 건 괜찮아?','그럼 닭가슴살 먹는 건 그런가?','그러면 밥이랑 계란 먹는 건 괜찮아?','점심에 한식뷔페 한 접시 먹어도 괜찮을까?','아침에 편의점에서 샌드위치 먹는 건 그런가?','저녁에 일반식으로 밥 먹는 건 괜찮아?'][i]
            elif family=='updated_goal':
                hist=[{'role':'user','content':f'이전 목표는 하루 {2600+i*20}kcal였어요.'},{'role':'assistant','content':'그때 목표를 참고했어요.'}]
                q=f'목표를 방금 바꿨어요. 지금 확인된 섭취량 {v["calories"]}kcal와 새 하루 목표 {v["target"]}kcal 기준으로 남은 열량만 알려주세요. 예전 목표는 쓰지 마세요.'
            elif family=='stale':
                hist=[{'role':'user','content':f'지난 상담 때는 {1300+i*33}kcal 먹었다고 했어요.'},{'role':'assistant','content':'이전 상담 수치를 확인했어요.'}]
                q=f'현재 확정 합계는 {v["calories"]}kcal로 수정됐고 목표는 {v["target"]}kcal예요. 이전 대화 합계 대신 지금 값으로 남은 양을 계산해줘요.'
            else:q=f'저녁에는 {ordinary[i]} 약속이 생겼어요. 아직 먹은 건 아니니 오늘 섭취량에는 넣지 말고, 점심에 굶지 않고 준비할 방법을 알려주세요.'
            if fields:expected='ask_required'
            out.append({'id':f'h5-{family}-{i:02d}','split':'evaluation','family':family,'question':q,'verified_context':v,'recent_messages':hist,'expected':expected,'required_fields':fields,'rationale':('Ask only essential absent fields; never invent an unseen product, recipe, referent or portion. Standard scaling needs consumed amount only; explicit individual recipe needs its missing inputs.' if fields else 'All facts needed for general advice or arithmetic are present. Answer directly using current verified values; no optional closing request or invented record.'),'provenance':'prospective_synthetic_holdout_authored_after_v4_frozen_before_any_new_model_outputs'})
    validate_cases(out);return out


def cohort_sha(rows):return digest(rows)


def assert_novel(rows):
    if len(rows)!=100 or len({x['question'] for x in rows})!=100:raise ValueError('100 unique question texts required')
    old=[]
    for p in [SOURCE/'frozen.json',SOURCE/'development.json',SOURCE.parent/'v3-candidate-20261022/development.json',SOURCE.parent/'execution-v2/development.json']:
        old+=read(p)
    if {c['question'] for c in rows}&{c['question'] for c in old}:raise ValueError('Exposed question overlap')
    return True


def supported(candidate):
    changed={n for n in candidate['snapshot']['texts'] if candidate['snapshot']['texts'][n]!=candidate['baseline']['texts'][n]}
    if changed!={'team.base','team.compact_followup'}:raise ValueError('Exactly the reviewed two-template combination required')
    frozen=read(SOURCE/'candidate.json')
    if candidate['snapshot']['texts']!=frozen['texts']:raise ValueError('Candidate differs from frozen v4; new development required')


def select(values):
    a,b=values['v1'],values['v4'];complete=all(v['expected']==v['judged']==100 and v['generation_failures']==0 and v['usage_complete'] for v in values.values())
    ok=complete and all(b[k]>=98 and b[k]>=a[k]-1 for k in ['correct','faithful']) and b['passed']>=max(98,a['passed']) and b['required_recall_numerator']>=49 and b['unsafe_commitments']==0 and b['fresh']==b['no_write']==100 and b['unnecessary_all']<=min(2,a['unnecessary_all']) and b['p95_ms']<=a['p95_ms']*1.25 and b['cost_usd']<=a['cost_usd']*1.25
    return {'holdout_passed':bool(ok),'evaluation_preferred':'v4' if ok else 'v1','production_adoption':False}


def code_sha():
    return {n:hashlib.sha256((ROOT/n).read_text(encoding='utf-8-sig').encode()).hexdigest() for n in ['backend/scripts/eval/clarification_holdout.py','backend/scripts/eval/run_clarification_holdout.py','backend/scripts/prompt_release_workflow.py']}


def validate(folder):
    folder=Path(folder);p=read(folder/'protocol.json');c=read(folder/'frozen.json')
    if p['code_sha256']!=code_sha() or p['cases_sha256']!=cohort_sha(c) or cohort_sha(c)!=COHORT_SHA or p['candidate_sha256']!=digest(read(folder/'candidate.json')):raise ValueError('Frozen holdout protocol changed')
    for name,h in p['historical_sha256'].items():
        if sha(SOURCE/name)!=h:raise ValueError('Historical evidence changed')
    assert_novel(c);return p


def verify(candidate,folder,key):
    """Recompute the gate and bindings, never sign an asserted summary flag."""
    from scripts.prompt_release_workflow import validate_candidate,identity
    from scripts.eval import run_clarification_holdout as runner
    from scripts.eval.clarification_execution import request_spec,price_usage
    from scripts.eval.clarification_cases import request_key
    from scripts.eval.clarification_v3 import fixture_truth,format_system,parse_grades
    from app.core.prompt_release_control import _snapshot
    validate_candidate(candidate,key);supported(candidate);folder=Path(folder);p=validate(folder)
    if read(folder/'candidate.json')!=candidate:raise ValueError('Approval candidate differs from evaluated exact commits')
    if identity(candidate['baseline'])!=identity(read(SOURCE/'source-answers.json')['snapshots']['v1']):raise ValueError('Historical baseline changed')
    if not read(SOURCE/'main/summary.json')['new_protocol_passed']:raise ValueError('Historical diagnostic gate failed')
    r=read(folder/'main/answers.json');j=read(folder/'main/judges.json');cs=read(folder/'frozen.json');by={c['id']:c for c in cs}
    if r['experiment']!=SUITE or r['conditions']!=CONDITIONS or r['cases_sha256']!=cohort_sha(cs) or r['protocol_sha256']!=digest(p) or r['runner_sha256']!=runner.runner_sha():raise ValueError('Execution identity changed')
    if identity(r['snapshots']['v1'])!=identity(candidate['baseline']) or identity(r['snapshots']['v4'])!=identity(candidate['snapshot']):raise ValueError('Evaluated snapshot mismatch')
    expected={(c['id'],l) for c in cs for l in ['v1','v4']};keys=[(a['case_id'],a['condition']) for a in r['rows']]
    if len(keys)!=200 or set(keys)!=expected:raise ValueError('Require200 unique attempts')
    coverage={l:{n:0 for n in ['team.base','team.compact_followup']} for l in ['v1','v4']}
    for a in r['rows']:
        snap=r['snapshots'][a['condition']];meta=_snapshot(snap).metadata();c=by[a['case_id']]
        if a['input_key']!=request_key(c,request_spec(snap)) or any(a['prompt_metadata'].get(k)!=meta[k] for k in ['prompt_commit_ids','prompt_hashes','prompt_bundle_sha256']):raise ValueError('Per-attempt binding changed')
        if a['status']!='completed' or a['no_write'] is not True or a['model']!=CONDITIONS['model'] or not a['answer']:raise ValueError('Incomplete/unsafe serving attempt')
        if any(type(a.get(k)) not in (int,float) or not math.isfinite(a[k]) or a[k]<0 for k in ['ms','cost_usd']) or abs(a['cost_usd']-price_usage(CONDITIONS['model'],a['usage']))>1e-9:raise ValueError('Invalid measured cost/duration')
        trace=read(folder/'main/model-inputs'/(a['case_id']+'-'+a['condition']+'.json'))
        if trace['input_key']!=a['input_key'] or trace['fixture_truth']!=fixture_truth(c):raise ValueError('Trace input/fixture mismatch')
        systems=[m['content'] for group in trace['model_inputs'] for m in group if m['type']=='system']
        used=[n for n in coverage[a['condition']] if snap['texts'][n] in systems]
        if not used:raise ValueError('Actual primary prompt application missing')
        for n in used:coverage[a['condition']][n]+=1
    if any(n<10 for c in coverage.values() for n in c.values()):raise ValueError('Two-template execution coverage incomplete')
    ids=[g['case_id'] for g in j['rows']]
    if len(ids)!=100 or set(ids)!=set(by):raise ValueError('Missing/duplicate grades')
    answers={(a['case_id'],a['condition']):a['answer'] for a in r['rows']};system=format_system(2)
    for i,c in enumerate(cs):
        g=next(g for g in j['rows'] if g['case_id']==c['id']);labels=['v1','v4'];order=labels[i%2:]+labels[:i%2];mapping=dict(zip('ab',order))
        payload={'case':c,'fixture_truth':fixture_truth(c),'historical_trace_limit':'Old answers have no full tool transcript; fixture facts are deterministic available truth, not proof of a tool read.',**{side:answers[(c['id'],l)] for side,l in mapping.items()}}
        if g['status']!='completed' or g['mapping']!=mapping or g['answer_binding']!=digest(payload) or g['system_sha256']!=hashlib.sha256(system.encode()).hexdigest() or g['n_conditions']!=2:raise ValueError('Judge answer/rubric binding changed')
        raw=read(folder/'main/raw-judges'/(c['id']+'.json'))
        if g['raw_sha256']!=digest(raw) or parse_grades(raw['text'],2)!=g['grades'] or raw['usage']!=g['usage']:raise ValueError('Raw grade differs from parsed scores')
        price_usage('gemini-3.1-pro-preview',[g['usage']])
    # Recompute without trusting mutable stored summary selection.
    with runner.bound():result=runner.summarize_stage(folder,False)
    if not result['holdout_passed']:raise ValueError('Candidate failed prospectively declared holdout gate')
    hashes={n:sha(folder/n) for n in ['protocol.json','candidate.json','frozen.json','main/answers.json','main/judges.json']}
    trace_hashes={str(f.relative_to(folder)).replace('\\','/'):sha(f) for pattern in ['main/model-inputs/*.json','main/raw-judges/*.json'] for f in folder.glob(pattern)}
    return {'schema_version':1,'suite':SUITE,'candidate_sha256':digest(candidate),'baseline_identity':identity(candidate['baseline']),'candidate_identity':identity(candidate['snapshot']),'condition':'v4','source_hashes':hashes,'trace_hashes':trace_hashes,'analysis':result,'coverage':coverage,'approved':True,'scope':'New synthetic100 paired holdout, same-author family controls, not live-user/clinical efficacy; unexercised templates inherit signed baseline'}
