"""Exercise real importer in session-local temporary tables, never mutate public data."""
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from check_render_beta import load_env, BACKEND
from import_food_catalog import apply_catalog, activate_version
from app.core.config import get_settings


def check():
    versions = ['recovery-' + uuid4().hex for _ in range(3)]
    report = {'scope': 'real_postgres_importer_session_local_temp_tables', 'checks': []}
    settings = get_settings()
    with psycopg.connect(settings.supabase_db_url, connect_timeout=10) as conn:
        original = conn.execute('select version from food_catalog_versions where active order by version').fetchall()
        conn.rollback()
        # pg_temp shadows unqualified importer table names. Even an accidental commit
        # cannot write or activate a public catalog version through these statements.
        conn.execute('create temporary table food_catalog_versions (like public.food_catalog_versions including all)')
        conn.execute('create temporary table food_catalog_items (like public.food_catalog_items including all)')
        assert conn.execute("select 'food_catalog_versions'::regclass::oid = 'pg_temp.food_catalog_versions'::regclass::oid").fetchone()[0]
        assert conn.execute("select 'food_catalog_items'::regclass::oid = 'pg_temp.food_catalog_items'::regclass::oid").fetchone()[0]
        conn.commit()
        with conn.transaction(force_rollback=True):
            conn.execute("set local lock_timeout='5s'")
            @contextmanager
            def borrowed(*args, **kwargs):
                # Importer contexts must neither commit nor close our outer test transaction.
                yield conn
            row = {'food_id': 'mfds:synthetic-recovery', 'name': '합성 복구 검증',
                   'normalized_name': '합성복구검증', 'source': 'mfds'}
            with patch('psycopg.connect', borrowed):
                apply_catalog([row], {'accepted': 1}, versions[0], 'a' * 64, True)
                apply_catalog([row], {'accepted': 1}, versions[0], 'a' * 64, True)
                assert conn.execute('select count(*) from food_catalog_items where version=%s', (versions[0],)).fetchone()[0] == 1
                report['checks'].append('repeat_import_single_row')
                apply_catalog([row], {'accepted': 1}, versions[1], 'b' * 64, True)
                activate_version(versions[0])
                assert conn.execute('select version from food_catalog_versions where active').fetchone()[0] == versions[0]
                report['checks'].append('previous_verified_version_restored')
                for action, reason in [
                    (lambda: apply_catalog([row], {'accepted': 1}, versions[0], 'c' * 64), 'version_content_conflict'),
                    (lambda: apply_catalog([row], {'accepted': 2}, versions[0], 'a' * 64), 'import_count_mismatch'),
                    (lambda: activate_version(versions[2]), 'unverified_version')]:
                    try:
                        action()
                    except ValueError as exc:
                        assert str(exc) == reason
                        report['checks'].append(reason + '_rejected')
                    else:
                        raise AssertionError(reason + '_not_rejected')
                assert conn.execute('select version from food_catalog_versions where active').fetchone()[0] == versions[0]
            # A separate connection still sees the public original catalog throughout.
            with psycopg.connect(settings.supabase_db_url, connect_timeout=10) as observer:
                assert observer.execute('select version from food_catalog_versions where active order by version').fetchall() == original
                assert observer.execute('select count(*) from food_catalog_versions where version=any(%s)', (versions,)).fetchone()[0] == 0
                report['checks'].append('public_observer_unchanged')
        assert conn.execute('select version from public.food_catalog_versions where active order by version').fetchall() == original
        assert conn.execute('select count(*) from food_catalog_versions where version=any(%s)', (versions,)).fetchone()[0] == 0
        report['checks'].append('forced_rollback_removes_all_fixtures')
    path = BACKEND.parent / 'docs/food_catalog/RECOVERY_INTEGRATION.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    load_env(BACKEND / '.env')
    check()
