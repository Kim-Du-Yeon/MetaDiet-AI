"""Shared deterministic food search and mass-based nutrition quotes."""
import hashlib
import logging
import math
from pydantic import Field, model_validator
from app.schemas.proposals import StrictModel
from app.tools.food_import import normalize_name

logger = logging.getLogger(__name__)
CSV_COLUMNS = {'calories': '에너지', 'protein_g': '단백질', 'carbs_g': '탄수화물',
               'fat_g': '지방', 'sodium_mg': '나트륨'}


class LabelNutrition(StrictModel):
    food_name: str = Field(min_length=1, max_length=200)
    manufacturer: str = Field(default='', max_length=200)
    basis_g: float = Field(gt=0, le=10000)
    quantity_g: float = Field(gt=0, le=10000)
    calories: float = Field(ge=0, le=30000)
    protein_g: float = Field(ge=0, le=10000)
    carbs_g: float = Field(ge=0, le=10000)
    fat_g: float = Field(ge=0, le=10000)
    sodium_mg: float | None = Field(default=None, ge=0, le=1000000)

    @model_validator(mode='after')
    def plausible(self):
        if self.calories / self.basis_g > 10 or any(
                getattr(self, key) > self.basis_g for key in ('protein_g', 'carbs_g', 'fat_g')):
            raise ValueError('implausible_label')
        return self


def calculate_quote(row: dict, quantity_g: float) -> dict:
    if not math.isfinite(quantity_g) or not 0 < quantity_g <= 10000:
        raise ValueError('invalid_quantity')
    nutrients = row['nutrients']
    for key in ('calories', 'protein_g', 'carbs_g', 'fat_g'):
        if nutrients.get(key) is None or not math.isfinite(float(nutrients[key])) or nutrients[key] < 0:
            raise ValueError('missing_nutrient_values')
    return {'food_name': row['name'], 'quantity_g': quantity_g, 'source': row['source'],
            **{k: round(v * quantity_g / 100, 1) if v is not None else None for k, v in nutrients.items()},
            'food_id': row['food_id'], 'nutrition_metadata': {
                k: row.get(k) for k in ('manufacturer', 'basis_g', 'basis_text', 'serving_text',
                'package_text', 'source_date', 'source_url', 'catalog_version') if row.get(k) is not None}}


def quote_label(label: LabelNutrition) -> dict:
    import json
    identity = hashlib.sha256(json.dumps(label.model_dump(), sort_keys=True).encode()).hexdigest()[:24]
    row = {'food_id': 'label:' + identity, 'name': label.food_name, 'source': 'user_label',
           'manufacturer': label.manufacturer, 'basis_g': label.basis_g, 'basis_text': f'{label.basis_g:g}g',
           'nutrients': {k: getattr(label, k) * 100 / label.basis_g if getattr(label, k) is not None else None
                         for k in CSV_COLUMNS}}
    return calculate_quote(row, label.quantity_g)


class FoodCatalog:
    def __init__(self, *, frame=None, repository=None):
        if frame is None:
            from app.tools.nutrition_db import _load_raw_df
            frame = _load_raw_df()
        self.frame = frame
        self.repository = repository
        self.rows = {}
        self.legacy_ids = {}
        for index, row in frame.iterrows():
            name = str(row.get('식품명', ''))
            code = str(row.get('식품코드', '')).strip()
            if not code or code == 'nan':
                code = hashlib.sha256(name.encode()).hexdigest()[:24]
            food_id = 'csv:' + code
            nutrients = {}
            for key, column in CSV_COLUMNS.items():
                try:
                    value = float(row[column])
                    nutrients[key] = value if math.isfinite(value) and value >= 0 else None
                except (KeyError, ValueError, TypeError):
                    nutrients[key] = None
            self.rows[food_id] = {'food_id': food_id, 'name': name, 'normalized_name': normalize_name(name),
                'source': 'csv', 'basis_g': 100, 'basis_text': '100g', 'manufacturer': '', 'nutrients': nutrients}
            self.legacy_ids[int(index)] = food_id

    async def search(self, query: str, limit: int = 20) -> list[dict]:
        normalized = normalize_name(query.strip())
        if not normalized or len(normalized) > 200 or not 1 <= limit <= 20:
            raise ValueError('invalid_query')
        local = [row for row in self.rows.values() if normalized in row['normalized_name']]
        remote = await self.repository.search(normalized, limit) if self.repository else []
        combined = list({row['food_id']: row for row in local + remote}.values())
        exact = [row for row in combined if row['normalized_name'] == normalized]
        match_type = 'exact' if exact else 'partial'
        if exact:
            combined = exact
        else:
            aliases = {'닭가슴살': '닭고기, 가슴, 생것', '현미밥': '멥쌀, 현미, 밥'}
            target = aliases.get(query.strip())
            alias_rows = [row for row in self.rows.values() if target and row['name'] == target]
            if alias_rows:
                combined = alias_rows
                match_type = 'verified_alias'
        combined.sort(key=lambda row: (row['name'], row.get('manufacturer', ''), row['food_id']))
        result = [{k: row.get(k) for k in ('food_id', 'name', 'source', 'manufacturer', 'basis_g',
                   'basis_text', 'package_text', 'catalog_version')} for row in combined[:limit]]
        self.rows.update((row['food_id'], row) for row in combined[:limit])
        for item in result:
            item['match_type'] = match_type
        logger.info('food_catalog_search', extra={'matches_count': len(result),
                    'sources': sorted({item['source'] for item in result}),
                    'result_status': 'ambiguous' if len(result) > 1 else 'found' if result else 'not_found'})
        return result

    async def lookup(self, food_id: str | int, quantity_g: float) -> dict:
        # Old evaluation fixtures/clients can still supply a CSV integer. Never return one in new search results.
        if isinstance(food_id, int):
            food_id = self.legacy_ids.get(food_id, '')
        row = self.rows.get(food_id)
        if row is None and self.repository:
            row = await self.repository.get(food_id)
        if row is None:
            raise ValueError('food_not_found')
        return calculate_quote(row, quantity_g)


def default_catalog() -> FoodCatalog:
    from app.core.config import get_settings
    from app.db.food_catalog import FoodRepository
    return FoodCatalog(repository=FoodRepository() if get_settings().food_catalog_enabled else None)
