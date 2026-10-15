"""Pinned, reviewed fallback rows. Never select an arbitrary live product.

These are approximate app representatives, not the user's actual brand.
Keep provenance even when the compact UI hides manufacturer details.
"""
REVIEWED_FOODS = {
    'mfds:P123-208020300-0054': {
        'food_id': 'mfds:P123-208020300-0054', 'name': '김치찌개',
        'normalized_name': '김치찌개', 'source': 'mfds',
        'manufacturer': '(주)푸르샨식품', 'basis_g': 100, 'basis_text': '100g',
        'package_text': '500g', 'serving_text': '200ml(g)',
        'source_code': 'P123-208020300-0054', 'source_date': '2026-06-18',
        'source_url': 'https://various.foodsafetykorea.go.kr/nutrient/general/down/historyList.do',
        'catalog_version': 'reviewed-app-2026-10-15',
        'nutrients': {'calories': 49.0, 'protein_g': 4.12, 'carbs_g': 5.27,
                      'fat_g': 1.24, 'sodium_mg': 413.0},
    },
}
