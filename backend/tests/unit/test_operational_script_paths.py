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
