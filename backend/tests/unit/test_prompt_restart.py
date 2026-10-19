from scripts.eval.verify_prompt_restart import verify_restart


def test_restart_uses_selected_prompt_and_restores_identical_v1(tmp_path):
    report = verify_restart(tmp_path)
    assert report['passed']
    assert report['scope'] == 'local_isolated_processes_not_render_deployment'
    assert [step['release'] for step in report['steps']] == ['v1', 'v2', 'v1', 'v999']
    first, changed, restored, invalid = report['steps']
    assert first['prompt_bundle_sha256'] == restored['prompt_bundle_sha256']
    assert first['effective_system_sha256'] == restored['effective_system_sha256']
    assert changed['effective_system_sha256'] != first['effective_system_sha256']
    assert invalid['returncode'] == 2
