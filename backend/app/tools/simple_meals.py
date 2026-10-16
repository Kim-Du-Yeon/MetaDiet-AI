"""Reviewed app portions, not universal measured serving sizes.

The fast parser must consume the entire request. Unknown food or advice falls
back to the existing Agent; it must never silently create a partial meal.
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.core.service_clock import service_today
from app.schemas.proposals import MealProposal
from app.tools.food_groups import match_food_group

# alias, exact catalog name, app serving grams, display unit, representative ID
PORTIONS = [
    (('돼지고기볶음(제육볶음)', '돼지고기볶음', '돼지고기 볶음', '매운 제육볶음', '매운제육볶음', '제육볶음', '제육 볶음', '제육'),
        '돼지고기볶음(제육볶음)', 200, '인분', 'mfds:D110-465000000-0001'),
    (('김치찌개', '김치 찌개'), '김치찌개', 200, '인분', 'mfds:P123-208020300-0054'),
    (('간장불고기', '간장 불고기', '소불고기', '소 불고기', '불고기'), '소불고기, 볶은것', 200, '인분', None),
    (('생 닭가슴살', '닭가슴살 생것'), '닭고기, 가슴, 생것', 100, '개', None),
    (('구운 닭가슴살', '닭가슴살 구운것'), '닭고기, 가슴, 구운것(팬)', 100, '개', None),
    (('삶은 닭가슴살', '닭가슴살', '닭 가슴살', '닭가슴', '달각슴살', '닭가슴샬', '닭가슴삶'), '닭고기, 가슴, 삶은것', 100, '개', None),
    (('현미밥',), '멥쌀, 현미, 밥', 200, '공기', None),
    (('쌀밥', '백미밥', '밥'), '멥쌀, 백미, 밥', 200, '공기', None),
    (('배추김치', '배추 김치', '김치'), '김치, 배추 김치', 40, '회분', None),
    (('삶은 계란', '삶은 달걀', '삶은계란', '삶은달걀', '계란', '달걀', '달걀삶은것'), '달걀, 삶은것', 50, '개', None),
    (('계란후라이', '계란 후라이', '계란프라이', '계란 프라이', '달걀프라이', '달걀 프라이'), '달걀, 부침(달걀프라이)', 50, '개', None),
    (('고등어구이', '구운 고등어'), '고등어, 구운것', 100, '회분', None),
    (('삼겹살구이', '구운 삼겹살', '삼겹살'), '돼지고기, 삼겹살, 구운것(팬)', 100, '회분', None),
    (('바나나',), '바나나, 생것', 100, '개', None),
    (('두부',), '두부', 100, '회분', None),
    (('찐 고구마', '찐고구마', '고구마', '고구먀'), '고구마, 찐것', 150, '개', None),
    (('찐 감자', '찐감자', '감자'), '감자, 대지, 찐것', 150, '개', None),
    (('군고구마', '구운 고구마', '구운고구마'), '고구마, 구운것', 150, '개', None),
    (('사과',), '사과, 생것', 200, '개', None),
    (('귤',), '귤, 온주밀감, 생것', 80, '개', None),
    (('딸기',), '딸기, 개량종, 생것', 20, '개', None),
    (('방울토마토', '방울 토마토'), '토마토, 방울토마토, 생것', 15, '개', None),
    (('토마토',), '토마토, 생것', 150, '개', None),
    (('아보카도',), '아보카도, 생것', 100, '개', None),
    (('저지방 우유', '저지방우유'), '우유, 저지방우유', 200, '컵', None),
    (('우유',), '우유', 200, '컵', None),
    (('플레인 요거트', '플레인요거트', '플레인 요구르트', '요거트', '요구르트', '요거뜨'), '요구르트, 호상, 플레인', 100, '회분', None),
    (('식빵',), '빵, 식빵, 우유', 30, '장', None),
    (('오트밀', '오트 밀', '오트밀가루'), '귀리, 오트밀', 30, '회분', None),
    (('데친 브로콜리', '브로콜리', '브로컬리'), '브로콜리, 데친것', 80, '회분', None),
    (('오이',), '오이, 다다기, 생것', 150, '개', None),
    (('당근',), '당근, 뿌리, 생것', 100, '개', None),
    (('아몬드',), '아몬드, 말린것', 20, '회분', None),
    (('호두',), '호두, 말린것', 20, '회분', None),
    (('볶은 땅콩', '땅콩'), '땅콩, 볶은것', 20, '회분', None),
    (('조미김', '김'), '김, 조미김, 구운것', 5, '회분', None),
    (('깍두기',), '김치, 깍두기', 40, '회분', None),
    (('라이스페이퍼', '라이스 페이퍼'), '라이스페이퍼', 10, '장', 'mfds:P108-007000300-0013'),
    (('소보로빵', '소보로 빵', '소보루빵', '소보루 빵', '곰보빵', '메론빵', '메론 빵', '멜론빵', '멜론 빵'), '빵, 곰보빵', 80, '개', None),
    (('단팥빵', '단팥 빵', '팥빵'), '빵, 팥빵', 80, '개', None),
    (('크림빵', '크림 빵'), '빵, 크림빵', 80, '개', None),
    (('베이글', '베이글빵'), '빵, 베이글', 100, '개', None),
    (('크루아상', '크로와상', '크로아상'), '빵, 크루아상', 60, '개', None),
    (('모닝빵', '모닝 빵'), '빵, 모닝빵', 30, '개', None),
    (('카스테라', '카스텔라'), '빵, 카스텔라', 80, '회분', None),
    (('도넛', '도너츠'), '빵, 도넛, 링', 60, '개', None),
    (('붕어빵',), '빵, 붕어빵, 팥', 50, '개', None),
    (('소시지빵', '소세지빵'), '빵, 소시지빵', 100, '개', None),
    (('피자', '냉동피자', '냉동 피자', '도미노피자', '도미노 피자', '피자헛 피자', '피자헛피자'), '피자, 콤비네이션 피자, 냉동, 전자레인지 조리', 100, '조각', None),
    (('불고기피자', '불고기 피자'), '피자, 불고기 피자, 냉동, 전자레인지 조리', 100, '조각', None),
    (('물만두', '물 만두'), '만두, 물만두', 15, '개', None),
    (('군만두', '군 만두', '군만듀'), '만두, 군만두', 30, '개', None),
    (('김치만두', '김치 만두'), '만두, 김치 만두', 30, '개', None),
    (('고기만두', '고기 만두', '찐만두', '만두', '만듀'), '만두, 고기 만두', 30, '개', None),
    (('햄버거', '버거'), '햄버거, 소고기패티, 토마토, 양상추, 양파', 200, '개', None),
    (('새우볶음밥', '새우 볶음밥'), '볶음밥, 새우 볶음밥', 300, '회분', None),
]
# App portions: these are editable defaults, not claims about a specific product.
CATEGORY_DEFAULTS = {
    '피자, 콤비네이션 피자, 냉동, 전자레인지 조리': (2, {'조각': 100, '판': 800, '회분': 200, '인분': 200}),
    '피자, 불고기 피자, 냉동, 전자레인지 조리': (2, {'조각': 100, '판': 800, '회분': 200, '인분': 200}),
    '만두, 물만두': (10, {'개': 15, '회분': 150, '인분': 150}),
    '만두, 군만두': (5, {'개': 30, '회분': 150, '인분': 150}),
    '만두, 김치 만두': (5, {'개': 30, '회분': 150, '인분': 150}),
    '만두, 고기 만두': (5, {'개': 30, '회분': 150, '인분': 150}),
}
COUNTS = {'한': 1, '하나': 1, '두': 2, '둘': 2, '세': 3, '네': 4, '다섯': 5, '여섯': 6, '반': .5}
# Longer aliases must win: 계란후라이 must not be consumed as 계란.
ALIASES = sorted(((alias, canonical, serving, unit, food_id)
    for aliases, canonical, serving, unit, food_id in PORTIONS for alias in aliases),
    key=lambda row: len(row[0]), reverse=True)
TYPO_DISPLAY = {'달각슴살': '닭가슴살', '닭가슴샬': '닭가슴살', '닭가슴삶': '닭가슴살',
    '고구먀': '고구마', '브로컬리': '브로콜리', '요거뜨': '요거트',
    '군만듀': '군만두', '만듀': '만두'}


def parse_simple_meal(message, *, forced_meal_type=None, allow_unknown=False):
    if not isinstance(message, str) or len(message) > 2000:
        return None
    text = message.strip()
    if allow_unknown and re.search(r'추천|계획|예정|알려|어떻게|\?|수정|삭제', text):
        return None
    today = service_today()
    day = today
    date_match = re.match(r'^(\d{4}-\d{2}-\d{2})\s+', text)
    if date_match:
        try:
            from datetime import date
            day = date.fromisoformat(date_match[1])
        except ValueError:
            return None
        if day > today:
            return None
        text = text[date_match.end():]
    for word, delta in [('그제', 2), ('어제', 1), ('오늘', 0)]:
        if text.startswith(word):
            day = today - timedelta(days=delta)
            text = text[len(word):].lstrip()
            break
    from app.core.config import get_settings
    hour = datetime.now(ZoneInfo(get_settings().service_timezone)).hour
    meal_type = 'breakfast' if hour < 11 else 'lunch' if hour < 16 else 'dinner'
    for word, kind in [('아침', 'breakfast'), ('점심', 'lunch'), ('저녁', 'dinner'), ('간식', 'snack')]:
        if text.startswith(word):
            meal_type = kind
            text = re.sub(r'^' + word + r'(?:에|으로)?\s*', '', text)
            break
    meal_type = forced_meal_type or meal_type
    text = re.sub(r'\s*(?:먹었어|먹었어요|먹었다|먹음|머겅써|먹엇어|기록해줘|기록해주세요|기록만(?:\s*해줘)?)[.!]?$', '', text)
    text = re.sub(r'(?:을|를|으\s*ㄹ|르)\s*$', '', text).rstrip()
    items = []
    while text.strip(' ,、'):
        text = text.lstrip(' ,、')
        matched = None
        group_match = None
        for candidate in ALIASES:
            if text.startswith(candidate[0]):
                tail = text[len(candidate[0]):]
                if allow_unknown and tail and not re.match(r'^[\s,\d]|^(?:이랑|랑|하고|와|과|한|두|반)', tail):
                    continue
                matched = candidate
                break
        possible_group = match_food_group(text)
        if possible_group and (not matched or len(possible_group[1]) > len(matched[0])):
            group_match = possible_group
            if group_match:
                group, alias, _ = group_match
                matched = (alias, group.canonical, group.serving_g, group.unit, None)
        if not matched:
            if not allow_unknown:
                return None
            unknown = re.match(r'([가-힣A-Za-z][가-힣A-Za-z ]*?)(?=\s*(?:\d|한|두|반)\s*(?:개|장|공기|g)|,|$|\s+(?:그리고|랑|하고)\s+)', text)
            if not unknown or len(unknown[1].strip()) > 100:
                return None
            alias = unknown[1].strip()
            # No implicit brand substitution: the user must choose a generic basis.
            serving = 70 if '돼지바' in alias or '아이스크림' in alias else 100
            matched = (unknown[1], None, serving, '개' if serving == 70 else '회분', None)
        alias, canonical, serving, default_unit, food_id = matched
        text = text[len(alias):].lstrip()
        default_amount, unit_grams = CATEGORY_DEFAULTS.get(canonical, (1, {default_unit: serving, '회분': serving, '인분': serving}))
        if group_match:
            group, _, unit_grams = group_match
            default_amount = group.count
        quantity = re.match(r'((?:\d+(?:\.\d+)?)|하나|한|둘|두|세|네|다섯|여섯|반)\s*(g|그램|공기|개|회분|인분|장|컵|조각|판)', text, re.I)
        amount, unit, defaulted = default_amount, default_unit, True
        if quantity:
            amount = COUNTS.get(quantity[1])
            if amount is None:
                amount = float(quantity[1])
            unit = quantity[2].lower()
            unit = 'g' if unit == '그램' else unit
            if unit not in (set(unit_grams) | {'g'} | ({'개', '장', '공기', '컵'} if canonical is None else set())):
                return None
            text = text[quantity.end():].lstrip()
            defaulted = False
            # Explicit mass overrides a preceding serving/count declaration.
            explicit_mass = re.match(r'(\d+(?:\.\d+)?)\s*(?:g|그램)', text, re.I)
            if explicit_mass:
                amount, unit = float(explicit_mass[1]), 'g'
                text = text[explicit_mass.end():].lstrip()
        grams = amount if unit == 'g' else amount * unit_grams.get(unit, serving)
        if not 0 < grams <= 10000:
            return None
        approximate = canonical in CATEGORY_DEFAULTS or canonical.startswith('빵,') or canonical == '소불고기, 볶은것' if canonical else False
        basis_note = ('곰보빵(소보로) 유사 기준이며 실제 메론빵 제품값이 아니에요.' if '메론' in alias or '멜론' in alias
            else '일반 콤비네이션 피자 기준이며 브랜드 제품값이 아니에요.' if '도미노' in alias or '피자헛' in alias
            else '앱 대표 기준으로 계산했어요. 제품·크기에 따라 달라요.' if approximate else '')
        if food_id == 'mfds:P123-208020300-0054':
            basis_note = '김치찌개 대표 기준·대략값이에요. 실제 제품·재료와 다를 수 있어요.'
        if food_id == 'mfds:D110-465000000-0001':
            basis_note = '식약처 가정식 제육볶음 대표값·대략값이에요. 1인분은 앱 기본 200g이며 수정할 수 있어요.'
        if group_match:
            approximate = True
            basis_note = f'{group.name} 음식군 대표값({canonical})으로 계산했어요. 실제 제품·재료와 다를 수 있어요.'
        items.append({'canonical': canonical, 'food_id': food_id, 'quantity_g': grams,
            **({'unresolved': True} if canonical is None else {}),
            'portion': {'display_name': TYPO_DISPLAY.get(alias, alias),
                'amount': amount, 'unit': unit, 'unit_g': serving,
                'default_unit': default_unit, 'defaulted': defaulted,
                'unit_grams': unit_grams, 'basis_note': basis_note,
                **({'food_group': group.name} if group_match else {}),
                'representative': bool(food_id) or approximate, 'policy_version': 'simple-v4'}})
        text = re.sub(r'^(?:그리고\s+|이랑\s*|랑\s*|하고\s*|와\s*|과\s*)', '', text)
        if len(items) > 30:
            return None
    if allow_unknown and items and all(i.get('unresolved') for i in items):
        if all(i['portion']['defaulted'] and not re.search(r'돼지바|아이스크림', i['portion']['display_name']) for i in items):
            return None
    return {'log_date': day.isoformat(), 'meal_type': meal_type, 'items': items} if items else None


async def calculate_simple_meal(parsed, catalog):
    meals = []
    for item in parsed['items']:
        food_id = item['food_id']
        if not food_id:
            matches = await catalog.search(item['canonical'], kind='standard')
            exact = [row for row in matches if row['name'] == item['canonical']]
            if len(exact) != 1:
                raise ValueError('reviewed_standard_unavailable')
            food_id = exact[0]['food_id']
        quote = await catalog.lookup(food_id, item['quantity_g'])
        if item['food_id'] and re.sub(r'\s+', '', quote['food_name']) != item['canonical']:
            raise ValueError('representative_identity_mismatch')
        quote['nutrition_metadata']['portion'] = item['portion']
        quote['meal_type'] = parsed['meal_type']
        meals.append(quote)
    return MealProposal(kind='intake', log_date=parsed['log_date'], meals=meals).model_dump(mode='json')
