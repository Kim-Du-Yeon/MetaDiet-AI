"""Fail-closed numeric strategy policy. Only server-reviewed claims authorize targets."""
import hashlib
import json
import math
from pathlib import Path
from app.rag.evidence_policy import POLICY_VERSION, resolve_claims

CATALOG = Path(__file__).with_name('reviewed_strategy_claims.json')
TARGETS = ('daily_calories', 'protein_g', 'carbs_g', 'fat_g')

def _normalized(value):
    return ''.join(str(value).split()).casefold()

def load_claims():
    # Do not cache: approval must see withdrawals/new editions immediately.
    data = json.loads(CATALOG.read_text(encoding='utf8'))
    if not isinstance(data, list):
        raise ValueError('Invalid reviewed claim catalog')
    return data

def evaluate_strategy(payload, profile, claims):
    context = profile.get('nutrition_policy_context')
    estimate = None
    goal_assessment = None
    if context is not None:
        from app.core.energy_policy import EnergyInputs, estimate_maintenance
        inputs = EnergyInputs(**context)
        for key in ('age','weight_kg','height_cm'):
            if profile.get(key) != getattr(inputs,key):
                raise ValueError('Profile changed since applicability confirmation')
        profile = {**profile,'policy_population':'adult','policy_conditions':'','gender':inputs.sex}
        estimate = estimate_maintenance(inputs)
        from app.core.goal_policy import assess_goal
        goal_assessment = assess_goal(profile,estimate['maintenance_kcal'])
    age = profile.get('age')
    if not isinstance(age, (int, float)) or not math.isfinite(age) or age < 18:
        raise ValueError('Adult applicability must be verified')
    region = profile.get('region') or 'KR'
    population = profile.get('policy_population')
    conditions = profile.get('policy_conditions')
    if population != 'adult' or conditions != '':
        raise ValueError('Explicit reviewed general-adult applicability is required')
    reviewed = [c for c in claims if c.get('review_status') == 'approved' and c.get('reviewer')]
    decisions = resolve_claims(reviewed, region=region, population=population, conditions=conditions)
    by_key = {d['claim_key']: d for d in decisions}
    adjustment_ready = bool(goal_assessment and goal_assessment['status'] == 'adjustment_ready')
    if adjustment_ready:
        adjustment = by_key.get('weight_loss_adjustment')
        if not adjustment or adjustment['status'] not in {'consistent', 'resolved_with_disclosure'}:
            raise ValueError('Reviewed weight-loss adjustment evidence is missing or conflicting')
        selected_adjustment = adjustment['selected']
        if (selected_adjustment.get('formula_version') != goal_assessment['policy_version']
                or goal_assessment['selected_deficit_kcal'] < selected_adjustment['low']
                or goal_assessment['selected_deficit_kcal'] > selected_adjustment['high']):
            raise ValueError('Goal adjustment does not match the reviewed policy')
        if payload['daily_calories'] != goal_assessment['target_calories']:
            raise ValueError('Proposed calories do not match the reviewed goal adjustment')
        if not any(all(e.get(k) == selected_adjustment.get(k) and e.get(k) for k in
                       ('source','page','document_sha256')) and selected_adjustment['excerpt'] in e.get('excerpt','')
                   for e in payload.get('evidence', [])):
            if not any(all(e.get(k) == selected_adjustment.get(k) and e.get(k) for k in
                           ('source','page','document_sha256')) and
                       _normalized(selected_adjustment['excerpt']) in _normalized(e.get('excerpt',''))
                       for e in payload.get('evidence', [])):
                raise ValueError('Selected weight-loss evidence was not cited')
    receipts = []
    for key in TARGETS:
        decision = by_key.get(key)
        if not decision or decision['status'] not in {'consistent', 'resolved_with_disclosure'}:
            raise ValueError('Reviewed applicable evidence is missing or conflicting: '+key)
        claim = decision['selected']
        if not any(all(e.get(k) == claim.get(k) and e.get(k) for k in
                       ('source','page','document_sha256')) and claim.get('excerpt') and
                   _normalized(claim['excerpt']) in _normalized(e.get('excerpt',''))
                   for e in payload.get('evidence',[])):
            raise ValueError('Selected latest evidence was not cited: '+key)
        value = payload[key]
        unit = claim['unit']
        tolerance = 0
        if key == 'daily_calories' and adjustment_ready:
            # Maintenance formula still establishes the baseline; the separate reviewed
            # adjustment claim authorizes the exact subtraction and safety floor.
            if not estimate or claim.get('formula_version') != estimate['policy_version']:
                raise ValueError('Reviewed maintenance formula inputs are required')
            value = 1
        elif key == 'daily_calories' and unit == 'maintenance_ratio':
            if not estimate or claim.get('formula_version') != estimate['policy_version']:
                raise ValueError('Reviewed maintenance formula inputs are required')
            value /= estimate['maintenance_kcal']
        elif key == 'daily_calories' and unit == 'kcal_per_day': pass
        elif key != 'daily_calories' and unit == 'g_per_day': pass
        elif key != 'daily_calories' and unit == 'g_per_kg':
            weight = profile.get('weight_kg')
            if not isinstance(weight,(int,float)) or not math.isfinite(weight) or weight <= 0:
                raise ValueError('Verified weight is required')
            value /= weight
        elif key != 'daily_calories' and unit == 'percent_energy':
            value = value * (9 if key == 'fat_g' else 4) / payload['daily_calories'] * 100
            tolerance = .01  # At most two-decimal gram rounding in the proposed allocation.
        else: raise ValueError('Unsupported explicit unit: '+unit)
        if not math.isfinite(value) or not claim['low']-tolerance <= value <= claim['high']+tolerance:
            raise ValueError('Proposed target exceeds reviewed bounds: '+key)
        receipts.append(decision)
    if adjustment_ready:
        receipts.append(by_key['weight_loss_adjustment'])
    catalog_sha = hashlib.sha256(json.dumps(claims,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'status':'approved','policy_version':POLICY_VERSION,'catalog_sha256':catalog_sha,
            'goal_assessment':goal_assessment,
            'calculation_context': {'inputs':context,'goal':profile.get('goal'),'estimate':estimate},
            'region':region,'population':population,'conditions':conditions,'decisions':receipts}
