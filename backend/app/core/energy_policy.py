"""KDRI 2025 maintenance estimate; never a weight-loss prescription or DB write."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

POLICY_VERSION = 'kdri2025-maintenance-v1'
SOURCE_SHA = '31c99fbf3a0253f55a5b9f53964ea9a1db8a108077650d119b4841a9b11f9cad'
PA = {
    'male': {'sedentary':1.0, 'low_active':1.11, 'active':1.25, 'very_active':1.48},
    'female': {'sedentary':1.0, 'low_active':1.12, 'active':1.27, 'very_active':1.45},
}


class EnergyInputs(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)
    age: float = Field(ge=19, lt=65)
    sex: Literal['male','female']
    weight_kg: float = Field(gt=0, le=500)
    height_cm: float = Field(gt=0, le=300)
    activity: Literal['sedentary','low_active','active','very_active']
    # Self-report: not a clinical clearance. No automatic inference from age alone.
    general_adult_confirmed: Literal[True]

    @field_validator('general_adult_confirmed', mode='before')
    @classmethod
    def require_explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('Explicit boolean confirmation is required')
        return value


def estimate_maintenance(inputs: EnergyInputs) -> dict:
    pa = PA[inputs.sex][inputs.activity]
    if inputs.sex == 'male':
        raw = 662 - 9.53*inputs.age + pa*(15.91*inputs.weight_kg + 539.6*inputs.height_cm/100)
    else:
        raw = 354 - 6.91*inputs.age + pa*(9.36*inputs.weight_kg + 726*inputs.height_cm/100)
    if raw <= 0:
        raise ValueError('Inputs produce a non-positive energy estimate')
    kcal = round(raw)
    # 55/20/25 is a service allocation, not a uniquely recommended KDRI ratio.
    return {
        'maintenance_kcal':kcal, 'raw_maintenance_kcal':raw,
        'protein_g':round(kcal*.20/4,2), 'carbs_g':round(kcal*.55/4,2),
        'fat_g':round(kcal*.25/9,2), 'is_applied':False,
        'policy_version':POLICY_VERSION, 'inputs':inputs.model_dump(),
        'activity_coefficient':pa,
        'allocation_percent':{'carbs':55,'protein':20,'fat':25},
        'reviewed_ranges_percent':{'carbs':[50,65],'protein':[10,20],'fat':[15,30]},
        'basis':{'source':'KDRI_2025_vol1.pdf','document_sha256':SOURCE_SHA,
                 'pages':[58,59,8], 'printed_pages':['16','17','viii'],
                 'source_url':'https://kns.or.kr/fileroom/fileroom_view.asp?BoardID=Kdr&idx=167'},
        'message':'유지 에너지의 추정치입니다. 감량·증량 목표나 저장된 전략이 아니며, '
                  '55/20/25 비율은 기준 범위 내 서비스 기본 배분입니다. '
                  '임신·수유, 질환별 영양관리 등 특수 상황에는 적용하지 않습니다.',
    }
