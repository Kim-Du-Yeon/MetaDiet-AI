import pytest


def test_frozen_identity_rejects_changed_inputs():
    from scripts.eval.rag_validation_support import validate_frozen
    with pytest.raises(ValueError):
        validate_frozen({'cases':[], 'translations':{}})


def test_failures_remain_in_quality_denominator():
    from scripts.eval.rag_validation_support import summarize_rows
    rows=[{'status':'completed','page_hit':True,'seconds':1,
           'judge':{'supported':True,'correct':True}},
          {'status':'failed','seconds':90,'error_type':'TimeoutError'}]
    result=summarize_rows(rows)
    assert result['attempts']==2 and result['failures']==1
    assert result['page_hit_rate']==.5 and result['supported_correct_rate']==.5
    assert result['all_attempt_p95_seconds']>1


def test_memory_gate_requires_real_duration_and_samples():
    from scripts.eval.rag_validation_support import memory_gate
    assert not memory_gate({'elapsed_seconds':10,'attempts':100,'failures':0,
        'samples':[]})['passed']


def test_long_idle_process_is_not_a_successful_soak():
    from scripts.eval.rag_validation_support import memory_gate
    result=memory_gate({'elapsed_seconds':7200,'attempts':0,'failures':0,
        'samples':[{'elapsed_seconds':i*20,'private_bytes':100000000,
                    'kiwi_loaded':False,'bm25_loaded':False} for i in range(361)]})
    assert not result['passed'] and not result['gates']['workload']


def test_safe_configuration_never_reads_application_env(monkeypatch):
    from scripts.eval.rag_validation_support import isolated_settings
    monkeypatch.setenv('SUPABASE_SERVICE_KEY','must-not-load')
    settings=isolated_settings({'GEMINI_API_KEY':'test','PINECONE_API_KEY':'test'})
    assert settings.supabase_service_key=='validation-disabled'
    assert settings.supabase_db_url=='' and settings.supabase_url.endswith('.invalid')
    assert settings.langsmith_tracing=='false'
