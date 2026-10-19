"""Button-first resolution. No domain writes and no invented nutrition."""
import hashlib
import json
from copy import deepcopy
from app.tools.simple_meals import calculate_simple_meal
from app.tools.food_catalog import LabelNutrition, quote_label
from app.schemas.proposals import MealProposal


def choice_card(parsed, request):
    items = []
    for index, item in enumerate(parsed['items']):
        if item.get('unresolved'):
            name = item['portion']['display_name']
            items.append({'index': index, 'query': name, 'quantity_g': item['quantity_g'],
                'generic_available': '아이스크림' in name or '돼지바' in name})
    identity = hashlib.sha256(json.dumps(parsed, sort_keys=True).encode()).hexdigest()
    return {'mode': 'meal_choices', 'id': identity, 'parsed': parsed, 'request': request, 'items': items,
            'known_count': len(parsed['items']) - len(items)}


async def resolve_meal_choices(parsed, choices, catalog):
    unresolved = {i for i, item in enumerate(parsed['items']) if item.get('unresolved')}
    indexed = {c['index']: c for c in choices}
    if len(indexed) != len(choices) or set(indexed) != unresolved:
        raise ValueError('resolve_every_unknown_once')
    meals, excluded = [], []
    for index, original in enumerate(parsed['items']):
        item = deepcopy(original)
        choice = indexed.get(index)
        if choice:
            name = item['portion']['display_name']
            if choice['action'] == 'exclude':
                excluded.append(name)
                continue
            if choice['action'] == 'label':
                label = LabelNutrition(**choice['label'])
                quote = quote_label(label)
                quote['nutrition_metadata']['requested_name'] = name
                quote['meal_type'] = parsed['meal_type']
                meals.append(quote)
                continue
            if choice['action'] != 'generic' or not ('아이스크림' in name or '돼지바' in name):
                raise ValueError('generic_unavailable')
            item.update(canonical='아이스크림, 바닐라맛', food_id=None)
            item['portion'].update(display_name=f'{name} (일반 아이스크림 기준)', representative=True)
        payload = await calculate_simple_meal({**parsed, 'items': [item]}, catalog)
        quote = payload['meals'][0]
        if choice:
            quote['nutrition_metadata']['substitution'] = {'requested_name': name,
                'basis_name': quote['food_name'], 'user_selected': True}
        meals.append(quote)
    if not meals:
        raise ValueError('all_foods_excluded')
    for meal in meals:
        meal['nutrition_metadata']['excluded_foods'] = excluded
        meal['nutrition_metadata']['button_resolution'] = True
    return MealProposal(kind='intake', log_date=parsed['log_date'], meals=meals).model_dump(mode='json')
