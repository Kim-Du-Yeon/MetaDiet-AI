from pathlib import Path


def test_backend_dir_is_script_parent_in_host_and_container_layouts():
    from scripts.check_postgres_pool_recovery import backend_dir

    assert backend_dir(Path("/app/scripts/check.py")) == Path("/app")
    assert backend_dir(Path("/workspace/repo/backend/scripts/check.py")) == Path("/workspace/repo/backend")


def test_docker_image_ships_proposal_migration_for_runtime_verification():
    root = Path(__file__).resolve().parents[3]
    dockerfile = (root / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert "supabase/migrations/20261008233749_agent_proposals.sql" in dockerfile
    assert "mkdir -p /app/artifacts" in dockerfile
    assert "chown app:app /app/artifacts" in dockerfile


def test_transaction_verifier_builds_strategy_from_current_policy():
    root = Path(__file__).resolve().parents[3]
    script = (root / "backend" / "scripts" / "check_proposal_transactions.py").read_text(encoding="utf-8")

    assert "baseline_payload(profile, None)" in script
    assert '"policy_version": "test"' not in script


def test_beta_feedback_checker_has_bounded_public_lifecycle_and_cleanup():
    root = Path(__file__).resolve().parents[3]
    script = (root / "backend" / "scripts" / "check_beta_feedback.py").read_text(encoding="utf-8")

    assert "timeout=180" in script
    assert "finally:" in script
    assert "synthetic" in script
    assert '"comment"' not in script
    assert '"client_submission_id"' in script
    assert "/feedback" in script
    assert "/users/me" in script


def test_beta_feedback_artifact_summary_is_redacted():
    from scripts.check_beta_feedback import redacted_summary

    result = redacted_summary(
        create_status=201,
        replay_status=200,
        rows_after_replay=1,
        rows_after_delete=0,
        create_ms=125.2,
        replay_ms=81.4,
    )

    assert result == {
        "status": "passed",
        "create_http_status": 201,
        "replay_http_status": 200,
        "rows_after_replay": 1,
        "rows_after_delete": 0,
        "create_ms": 125.2,
        "replay_ms": 81.4,
    }
    assert "comment" not in result
    assert "token" not in result
