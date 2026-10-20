"""Request-scoped, allowlisted answer provenance; never infers citations from retrieval."""
import re


def build_answer_basis(response, *, profile=None, intake=None, quotes=None, evidence=None,
                       search_attempted=False, search_status=None):
    evidence = evidence or {}
    cited = []
    def citation(match):
        key = match.group(1)
        if key not in evidence:
            return ''
        if key not in cited:
            cited.append(key)
        return f'[근거 {cited.index(key) + 1}]'
    response = re.sub(r'\[근거:([a-zA-Z0-9_-]+)\]', citation, response)
    documents = [{k: evidence[key].get(k) for k in ('source', 'page', 'source_url', 'excerpt')}
                 for key in cited]
    strategy = (profile or {}).get('strategy') or {}
    meals = (intake or {}).get('meals') or []
    totals = {key: round(sum(float(m.get(key) or 0) for m in meals), 1)
              for key in ('calories', 'protein_g', 'carbs_g', 'fat_g')}
    targets = {key: strategy.get(key) for key in ('daily_calories', 'protein_g', 'carbs_g', 'fat_g')}
    calculations = []
    for quote in (quotes or {}).values():
        metadata = quote.get('nutrition_metadata') or {}
        calculations.append({'food_name': quote.get('food_name'), 'source': quote.get('source'),
            'basis': (metadata.get('portion') or {}).get('basis_note'), 'food_id': quote.get('food_id')})
    status = ('cited' if documents else 'retrieved_not_cited' if evidence
              else 'search_unavailable' if search_attempted and search_status == 'search_unavailable'
              else 'insufficient_evidence' if search_attempted else 'not_searched')
    limitation = ('검색 도구 오류로 문서 근거를 확인하지 못했어요.' if status == 'search_unavailable' else
        '검색한 자료는 있지만 답변의 명시적 인용을 확인하지 못했어요.'
        if evidence and not documents else '관련 문서 근거를 확보하지 못했어요.' if search_attempted and not evidence
        else '이번 답변에서는 문서 검색을 수행하지 않았어요.' if not search_attempted else None)
    return response, {'records': {'date': intake.get('date'), 'meals': [
        {'food_name': m.get('food_name'), 'meal_type': m.get('meal_type'), 'quantity_g': m.get('quantity_g')}
        for m in meals], 'totals': totals} if intake is not None else None,
        'targets': targets if profile is not None else None,
        'calculations': calculations, 'documents': documents, 'limitation': limitation,
        'search': {'status': status},
        'notice': '답변 작성 당시 조회한 기록이에요. 미기록 식사는 포함되지 않아요.'}
