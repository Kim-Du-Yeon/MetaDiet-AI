"""Reviewed names, stable catalog IDs and editable app portions in one registry.

No network or model work at import/request time. Catalog values are copied from
official source snapshots; missing foods never inherit an arbitrary search hit.
"""
import json
import math
from pathlib import Path


def load_registry(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    aliases = set()
    rows = {row['food_id']: row for row in data['catalog_rows']}
    if len(rows) != len(data['catalog_rows']):
        raise ValueError('duplicate_representative_id')
    for row in rows.values():
        if (row.get('food_kind') != 'standard' or row.get('manufacturer')
                or row.get('basis_g') != 100 or not row.get('source_url')):
            raise ValueError('invalid_representative_source')
        for key in ('calories', 'protein_g', 'carbs_g', 'fat_g'):
            value = row['nutrients'].get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError('invalid_representative_nutrient')
    for food in data['foods']:
        if not 0 < food['serving_g'] <= 10000 or not food['basis_note']:
            raise ValueError('invalid_representative_portion')
        if food['food_id'].startswith('mfds:'):
            if food['food_id'] not in rows or rows[food['food_id']]['name'] != food['canonical']:
                raise ValueError('representative_identity_mismatch')
        for alias in food['aliases']:
            if not alias or alias in aliases:
                raise ValueError('duplicate_representative_alias')
            aliases.add(alias)
    return data


REGISTRY = load_registry(Path(__file__).with_suffix('.json'))
REPRESENTATIVE_FOODS = REGISTRY['foods']
REPRESENTATIVE_ROWS = {row['food_id']: row for row in REGISTRY['catalog_rows']}
REPRESENTATIVE_BY_CANONICAL = {food['canonical']: food for food in REPRESENTATIVE_FOODS}
