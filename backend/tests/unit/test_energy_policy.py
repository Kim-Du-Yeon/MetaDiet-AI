import pytest
from pydantic import ValidationError
from app.core.energy_policy import EnergyInputs, estimate_maintenance


def inputs(**changes):
    return EnergyInputs(**{'age':24, 'sex':'male', 'weight_kg':69.1,
        'height_cm':174.8, 'activity':'low_active',
        'general_adult_confirmed':True, **changes})


@pytest.mark.parametrize('changes,expected', [({},2701),
    ({'sex':'female','weight_kg':55.9,'height_cm':161.5},2087),
    ({'age':39.5,'weight_kg':68,'height_cm':173.4},2525),
    ({'age':39.5,'sex':'female','weight_kg':54.8,'height_cm':160},1957)])
def test_matches_kdri_worked_examples(changes,expected):
    result=estimate_maintenance(inputs(**changes))
    assert abs(result['maintenance_kcal']-expected)<=1
    assert result['is_applied'] is False
    assert result['basis']['pages']==[58,59,8]
    assert len(result['basis']['document_sha256'])==64


@pytest.mark.parametrize('changes', [{'age':18},{'age':65},{'weight_kg':float('nan')},
    {'height_cm':float('inf')},{'sex':'unknown'},{'activity':'unknown'},
    {'general_adult_confirmed':False},{'weight_kg':True},{'height_cm':True},
    {'age':True},{'general_adult_confirmed':1}])
def test_invalid_or_unconfirmed_context_rejected(changes):
    with pytest.raises((ValidationError,ValueError)):
        estimate_maintenance(inputs(**changes))


def test_activity_not_defaulted_and_macro_allocation_balances():
    with pytest.raises(ValidationError):
        EnergyInputs(age=30,sex='male',weight_kg=70,height_cm=170,
                     general_adult_confirmed=True)
    r=estimate_maintenance(inputs())
    assert abs(4*r['protein_g']+4*r['carbs_g']+9*r['fat_g']-r['maintenance_kcal'])<1
    assert estimate_maintenance(inputs(activity='active'))['maintenance_kcal']>r['maintenance_kcal']


async def test_preview_endpoint_does_not_write(fake_sb,mock_current_user):
    from app.api.routes.main import preview_energy
    r=await preview_energy(inputs(),auth_id=mock_current_user)
    assert r['is_applied'] is False
    assert not fake_sb.calls
