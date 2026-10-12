"""Strict MFDS import normalization. No network or database writes in this module."""
import math
import re
import unicodedata
from collections import Counter
from typing import Iterable

NUTRIENTS = {'calories': '에너지(kcal)', 'protein_g': '단백질(g)',
             'carbs_g': '탄수화물(g)', 'fat_g': '지방(g)', 'sodium_mg': '나트륨(mg)'}
SOURCE_URL = 'https://various.foodsafetykorea.go.kr/nutrient/general/down/historyList.do'


def normalize_name(value: str) -> str:
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).casefold()


def number(value) -> float:
    result = float(str(value).strip().replace(',', ''))
    if not math.isfinite(result) or result < 0:
        raise ValueError('invalid_nutrient')
    return result


def normalize_row(row: dict) -> dict:
    row = {str(k).strip(): v for k, v in row.items()}
    code, name = str(row.get('식품코드') or '').strip(), str(row.get('식품명') or '').strip()
    if not code or not name:
        raise ValueError('missing_identity')
    basis = str(row.get('영양성분함량 기준량', row.get('영양성분함량기준량', ''))).strip()
    matched = re.fullmatch(r'(\d+(?:\.\d+)?)\s*[gG]', basis)
    if not matched or not math.isfinite(float(matched[1])) or float(matched[1]) <= 0:
        raise ValueError('unknown_mass_basis')
    grams = float(matched[1])
    nutrients = {}
    for key, column in NUTRIENTS.items():
        value = row.get(column)
        if key == 'sodium_mg' and (value is None or str(value).strip() == ''):
            nutrients[key] = None
            continue
        try:
            nutrients[key] = number(value) * 100 / grams
        except (TypeError, ValueError):
            raise ValueError('missing_or_invalid_' + key) from None
    if nutrients['calories'] > 1000 or any(nutrients[k] > 100 for k in ('protein_g', 'carbs_g', 'fat_g')):
        raise ValueError('implausible_nutrients')
    return {'food_id': 'mfds:' + code, 'source': 'mfds', 'source_code': code, 'name': name,
            'normalized_name': normalize_name(name), 'manufacturer': str(row.get('제조사명') or '').strip(),
            'basis_g': grams, 'basis_text': basis, 'serving_text': str(row.get('1회 섭취참고량') or ''),
            'package_text': str(row.get('식품중량') or ''), 'barcode': str(row.get('바코드') or ''),
            'source_date': str(row.get('데이터생성일자') or ''), 'source_url': SOURCE_URL,
            'nutrients': nutrients}


def normalize_rows(raw_rows: Iterable[dict]) -> tuple[list[dict], dict]:
    rows, conflicts, reasons = {}, set(), Counter()
    total, duplicates = 0, 0
    for raw in raw_rows:
        total += 1
        try:
            row = normalize_row(raw)
        except ValueError as error:
            reasons[str(error)] += 1
            continue
        code = row['source_code']
        if code in conflicts:
            continue
        if code in rows:
            if rows[code] == row:
                duplicates += 1
            else:
                conflicts.add(code)
                del rows[code]
        else:
            rows[code] = row
    return list(rows.values()), {'total': total, 'accepted': len(rows), 'rejected': sum(reasons.values()),
                                 'duplicates': duplicates, 'conflicts': len(conflicts), 'reasons': dict(reasons)}
