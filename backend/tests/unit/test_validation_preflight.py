import importlib.util
from pathlib import Path
import pytest


def harness():
    spec=importlib.util.spec_from_file_location('validation_preflight',Path(__file__).resolve().parents[2]/'scripts/validation_preflight.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def configuration():
    return {'VALIDATION_API_URL':'https://metadiet-api-validation.onrender.com',
            'VALIDATION_PROJECT_REF':'abcdefghijklmnopqrst',
            'SUPABASE_URL':'https://abcdefghijklmnopqrst.supabase.co',
            'SUPABASE_DB_URL':'postgresql://postgres:fixture@db.abcdefghijklmnopqrst.supabase.co:5432/postgres',
            'ENABLE_SCHEDULER':'false','ENVIRONMENT':'validation','LANGSMITH_TRACING':'false',
            'VALIDATION_DURATION_SECONDS':'7200','VALIDATION_SESSIONS':'3',
            'VALIDATION_INTERVAL_SECONDS':'30','VALIDATION_SYNTHETIC_ONLY':'true'}


def test_requires_explicit_configuration_and_has_no_production_fallback():
    module=harness()
    assert module.validate_configuration(configuration())['configuration_only'] is True
    with pytest.raises(ValueError):module.validate_configuration({})


@pytest.mark.parametrize('field,value',[
    ('VALIDATION_API_URL','https://metadiet-api.onrender.com'),
    ('SUPABASE_URL','https://xznckgjdruxowbgzqamd.supabase.co'),
    ('SUPABASE_DB_URL','postgresql://postgres.xznckgjdruxowbgzqamd:fixture@aws-0-ap-northeast-2.pooler.supabase.com/postgres'),
    ('SUPABASE_DB_URL','postgresql://postgres:fixture@unrelated-db.invalid/postgres'),
    ('VALIDATION_PROJECT_REF','cxjglgodsdymrseuyett'),
    ('ENABLE_SCHEDULER','true'),('ENVIRONMENT','beta'),
    ('VALIDATION_DURATION_SECONDS','600'),('VALIDATION_SESSIONS','0'),
    ('VALIDATION_INTERVAL_SECONDS','0'),('VALIDATION_SYNTHETIC_ONLY','false'),
])
def test_rejects_existing_resources_and_unsafe_or_insufficient_conditions(field,value):
    values=configuration();values[field]=value
    with pytest.raises(ValueError):harness().validate_configuration(values)


def test_summary_never_contains_credentials():
    values=configuration();values['SUPABASE_SERVICE_KEY']='private-test-key'
    result=harness().validate_configuration(values)
    assert 'private-test-key' not in str(result) and 'fixture' not in str(result)
    assert result['planned_requests_per_session']>=100


def test_invalid_url_diagnostics_do_not_echo_input():
    values=configuration();values['VALIDATION_API_URL']='https://metadiet-api-validation.onrender.com:secret-port/'
    with pytest.raises(ValueError,match='^invalid_target_url$'):harness().validate_configuration(values)
