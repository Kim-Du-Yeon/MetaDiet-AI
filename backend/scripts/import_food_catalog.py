"""MFDS full-file import; dry-run by default. Only --apply/--activate writes Postgres."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.tools.food_files import read_rows
from app.tools.food_import import normalize_rows


def apply_catalog(rows, report, version, digest, activate=False):
    import psycopg
    from psycopg.types.json import Jsonb
    from app.core.config import get_settings
    with psycopg.connect(get_settings().supabase_db_url, connect_timeout=10) as conn:
        conn.execute("set local statement_timeout='120s'")
        conn.execute("select pg_advisory_xact_lock(hashtext('food_catalog_activation'))")
        prior = conn.execute('select raw_sha256 from food_catalog_versions where version=%s', (version,)).fetchone()
        if prior and prior[0] != digest:
            raise ValueError('version_content_conflict')
        if not prior:
            conn.execute('insert into food_catalog_versions(version,source,raw_sha256,report,verified) values(%s,\'mfds\',%s,%s,true)',
                         (version, digest, Jsonb(report)))
            with conn.cursor().copy('copy food_catalog_items(version,food_id,normalized_name,payload) from stdin') as copy:
                for row in rows:
                    copy.write_row((version, row['food_id'], row['normalized_name'], Jsonb(row)))
        count = conn.execute('select count(*) from food_catalog_items where version=%s', (version,)).fetchone()[0]
        if count != report['accepted']:
            raise ValueError('import_count_mismatch')
        if activate:
            conn.execute("update food_catalog_versions set active=false where source='mfds' and active")
            conn.execute('update food_catalog_versions set active=true where version=%s and verified', (version,))


def activate_version(version):
    import psycopg
    from app.core.config import get_settings
    with psycopg.connect(get_settings().supabase_db_url, connect_timeout=10) as conn:
        conn.execute("select pg_advisory_xact_lock(hashtext('food_catalog_activation'))")
        row = conn.execute('select verified,report from food_catalog_versions where version=%s', (version,)).fetchone()
        if not row or not row[0]:
            raise ValueError('unverified_version')
        count = conn.execute('select count(*) from food_catalog_items where version=%s', (version,)).fetchone()[0]
        if count != row[1]['accepted']:
            raise ValueError('import_count_mismatch')
        conn.execute("update food_catalog_versions set active=false where source='mfds' and active")
        conn.execute('update food_catalog_versions set active=true where version=%s', (version,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, nargs='?')
    parser.add_argument('--version', required=True)
    parser.add_argument('--expected-rows', type=int)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    if args.input is None:
        if not args.activate:
            parser.error('input required unless --activate restores an existing version')
        activate_version(args.version)
        return
    with args.input.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    rows, report = normalize_rows(read_rows(args.input))
    report.update(version=args.version, raw_sha256=digest)
    complete = args.expected_rows is not None and report['total'] == args.expected_rows
    report['complete'] = complete
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    if args.apply:
        if not complete or not rows or report['conflicts']:
            raise ValueError('incomplete_or_conflicting_catalog')
        apply_catalog(rows, report, args.version, digest, args.activate)
    elif args.activate:
        parser.error('--activate with input requires --apply')


if __name__ == '__main__':
    main()
