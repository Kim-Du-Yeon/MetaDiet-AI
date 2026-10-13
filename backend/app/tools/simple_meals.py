"""Reviewed app portions, not universal measured serving sizes.

The fast parser must consume the entire request. Unknown food or advice falls
back to the existing Agent; it must never silently create a partial meal.
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.core.service_clock import service_today
from app.schemas.proposals import MealProposal

# alias, exact catalog name, app serving grams, display unit, representative ID
PORTIONS = [
    (('생 닭가슴살', '닭가슴살 생것'), '닭고기, 가슴, 생것', 100, '개', None),
    (('구운 닭가슴살', '닭가슴살 구운것'), '닭고기, 가슴, 구운것(팬)', 100, '개', None),
    (('삶은 닭가슴살', '닭가슴살', '달각슴살'), '닭고기, 가슴, 삶은것', 100, '개', None),
    (('현미밥',), '멥쌀, 현미, 밥', 200, '공기', None),
    (('쌀밥', '백미밥', '밥'), '멥쌀, 백미, 밥', 200, '공기', None),
    (('배추김치', '김치'), '김치, 배추 김치', 40, '회분', None),
    (('삶은 계란', '삶은 달걀', '계란', '달걀'), '달걀, 삶은것', 50, '개', None),
    (('고등어구이', '구운 고등어'), '고등어, 구운것', 100, '회분', None),
    (('삼겹살구이', '구운 삼겹살'), '돼지고기, 삼겹살, 구운것(팬)', 100, '회분', None),
    (('바나나',), '바나나, 생것', 100, '개', None),
    (('두부',), '두부', 100, '회분', None),
    (('라이스페이퍼', '라이스 페이퍼'), '라이스페이퍼', 10, '장', 'mfds:P108-007000300-0016'),
]
COUNTS = {'한': 1, '하나': 1, '두': 2, '둘': 2, '세': 3, '반': .5}


def parse_simple_meal(message, *, forced_meal_type=None):
    if not isinstance(message, str) or len(message) > 2000:
        return None
    text = message.strip()
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
    text = re.sub(r'\s*(?:먹었어|먹었어요|먹었다|먹음|기록해줘|기록해주세요)[.!]?$', '', text)
    items = []
    while text.strip(' ,、'):
        text = text.lstrip(' ,、')
        matched = None
        for aliases, canonical, serving, unit, food_id in PORTIONS:
            for alias in aliases:
                if text.startswith(alias):
                    matched = (alias, canonical, serving, unit, food_id)
                    break
            if matched:
                break
        if not matched:
            return None
        alias, canonical, serving, default_unit, food_id = matched
        text = text[len(alias):].lstrip()
        quantity = re.match(r'((?:\d+(?:\.\d+)?)|하나|한|둘|두|세|반)\s*(g|그램|공기|개|회분|인분|장)', text, re.I)
        amount, unit, defaulted = 1, default_unit, True
        if quantity:
            amount = COUNTS.get(quantity[1])
            if amount is None:
                amount = float(quantity[1])
            unit = quantity[2].lower()
            unit = 'g' if unit == '그램' else unit
            if unit not in {default_unit, 'g', '회분', '인분'}:
                return None
            text = text[quantity.end():].lstrip()
            defaulted = False
            # Explicit mass overrides a preceding serving/count declaration.
            explicit_mass = re.match(r'(\d+(?:\.\d+)?)\s*(?:g|그램)', text, re.I)
            if explicit_mass:
                amount, unit = float(explicit_mass[1]), 'g'
                text = text[explicit_mass.end():].lstrip()
        grams = amount if unit == 'g' else amount * serving
        if not 0 < grams <= 10000:
            return None
        items.append({'canonical': canonical, 'food_id': food_id, 'quantity_g': grams,
            'portion': {'display_name': '닭가슴살' if alias == '달각슴살' else alias,
                'amount': amount, 'unit': unit, 'unit_g': serving,
                'default_unit': default_unit, 'defaulted': defaulted,
                'representative': bool(food_id), 'policy_version': 'simple-v1'}})
        if len(items) > 30:
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
