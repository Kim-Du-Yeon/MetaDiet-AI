from unittest.mock import Mock


def test_remote_index_delay_does_not_create_false_publication_failure(monkeypatch):
    from scripts.eval.publish_frozen_rerank import verify_run_count
    client = Mock()
    client.list_runs.side_effect = [[object()], [object(), object()]]
    monkeypatch.setattr("scripts.eval.publish_frozen_rerank.time.sleep", lambda seconds: None)
    assert verify_run_count(client, "experiment", 2) == 2
