"""Reviewed food-family fallback. Nutrition always comes from a catalog row."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class FoodGroup:
    name: str
    suffix: str
    canonical: str
    serving_g: int
    unit: str
    count: int = 1


# Specific families precede broader ones (zero soda before soda, fried rice before rice).
FOOD_GROUPS = (
    FoodGroup('제로 탄산', '제로콜라|제로사이다', '탄산 음료, 저칼로리콜라', 200, '컵'),
    FoodGroup('피자', '피자', '피자, 콤비네이션 피자, 냉동, 전자레인지 조리', 100, '조각', 2),
    FoodGroup('만두', '만두|만듀', '만두, 고기 만두', 30, '개', 5),
    FoodGroup('볶음밥', '볶음밥', '볶음밥', 300, '회분'),
    FoodGroup('빵', '빵', '빵, 곰보빵', 80, '개'),
    FoodGroup('치킨', '치킨', '닭고기, 살코기, 튀긴것(튀김옷)', 150, '회분'),
    FoodGroup('버거', '버거', '햄버거, 소고기패티, 토마토, 양상추, 양파', 200, '개'),
    FoodGroup('샌드위치', '샌드위치', '샌드위치, 햄, 치즈, 채소', 200, '개'),
    FoodGroup('쿠키', '쿠키', '과자, 쿠키, 버터', 30, '개'),
    FoodGroup('케이크', '케이크|케익', '케이크, 스펀지 케이크', 100, '조각'),
    FoodGroup('아이스크림', '아이스크림', '아이스크림, 바닐라맛', 70, '개'),
    FoodGroup('주스', '주스|쥬스', '오렌지 주스', 200, '컵'),
    FoodGroup('탄산', '콜라|사이다|탄산음료', '탄산 음료, 콜라', 200, '컵'),
    FoodGroup('요거트', '요거트|요구르트', '요구르트, 호상, 플레인', 100, '회분'),
    FoodGroup('라면', '라면', '라면, 조리후', 500, '회분'),
    FoodGroup('파스타', '파스타|스파게티', '스파게티', 300, '회분'),
    FoodGroup('감자튀김', '감자튀김', '감자 튀김, 튀긴것', 100, '회분'),
    FoodGroup('아메리카노', '아메리카노', '커피, 아메리카노(2샷)', 200, '컵'),
)
BRAND_PREFIX = r'(?:(?:파리바게뜨|뚜레쥬르|교촌|굽네|BHC|bbq|도미노|수제|일반|냉동)\s+)?'
BOUNDARY = r'(?=$|[\s,\d]|(?:한|두|세|네|반)(?:개|장|조각|판|컵|회분|인분)|이랑|랑|하고|와|과)'


def match_food_group(text: str):
    if re.search(r'사료|반려|세제|장난감|사진|영양제', text.split(',')[0]):
        return None
    for group in FOOD_GROUPS:
        # No arbitrary first search result, substring match, or LLM-created nutrients.
        match = re.match(BRAND_PREFIX + r'[가-힣A-Za-z]{0,24}(?:' + group.suffix + ')' + BOUNDARY, text)
        if match:
            alias = match[0].strip()
            units = {group.unit: group.serving_g, '회분': group.serving_g * group.count,
                     '인분': group.serving_g * group.count}
            if group.name == '피자':
                units['판'] = 800
            return group, alias, units
    return None
