from pathlib import Path
from unittest.mock import Mock


def test_probe_cleanup_reauthenticates_instead_of_refreshing_old_token(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'scripts'))
    import check_admin_feedback as probe
    fixture = tmp_path / '.env.fixture'
    fixture.write_text('synthetic fixture', encoding='utf-8')
    monkeypatch.setattr(probe, 'ENV', fixture)
    monkeypatch.setattr(probe, 'ARTIFACT', tmp_path / 'result.json')
    for key,value in {'AUTH_ID':'fixture-auth','TOKEN':'old-token','ID':'fixture-feedback',
                      'EMAIL':'fixture@example.invalid','PASSWORD':'test-only-password'}.items():
        monkeypatch.setenv('ADMIN_FEEDBACK_'+key,value)
    service = Mock(side_effect=[{'access_token':'fresh-password-token'},[],[]])
    delete = Mock(return_value={'status':'deleted'})
    monkeypatch.setattr(probe, 'service_api', service)
    monkeypatch.setattr(probe, 'json_request', delete)
    probe.cleanup()
    assert service.call_args_list[0].args == ('/auth/v1/token?grant_type=password','POST',{
        'email':'fixture@example.invalid','password':'test-only-password'})
    assert delete.call_args.kwargs['token'] == 'fresh-password-token'
    assert not fixture.exists()
