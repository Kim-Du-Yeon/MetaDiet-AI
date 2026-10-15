"""Offline summary of the published, synthetic-only Render recovery evidence."""
import hashlib
import json
from pathlib import Path
from render_validation_common import summarize
from check_feedback_scale import frozen_cases

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/admin-feedback'


def run():
    soak=json.loads((OUT/'render-free-soak.json').read_text())
    restore=json.loads((OUT/'render-free-restore.json').read_text())
    assert soak['passed'] and restore['passed']
    assert len(soak['requests'])==720 and len(soak['races'])==100
    # First complete cycle of 100 frozen cases per phase, all three sessions.
    # Rotated ordering is retained; there is no randomized optimization claim.
    paired={}
    for phase in ['before_restart','after_restart']:
        rows=[r for r in soak['requests'] if r['phase']==phase]
        rounds=sorted({r['round'] for r in rows})[:100]
        assert len(rounds)==100 and len({r%100 for r in rounds})==100
        selected=[r for r in rows if r['round'] in rounds]
        paired[phase]=summarize(selected,300)
    result={'scope':soak['scope'],'deployment_commit':soak['deployment_commit'],
        'frozen_cases_sha256':hashlib.sha256(json.dumps(frozen_cases(),sort_keys=True).encode()).hexdigest(),
        'soak_seconds':soak['observed_seconds'],'all_soak_requests':soak['summary'],
        'same_100_cases_three_sessions':paired,
        'health_attempts':len(soak['health_checks']),
        'health_failures':sum(not r['ok'] for r in soak['health_checks']),
        'race_rounds':len(soak['races']),'race_rounds_passed':sum(r['ok'] for r in soak['races']),
        'race_write_attempts':300,
        'restart_confirmed':soak['restart_observed'],
        'old_connection_error_type':soak['old_connection_error_type'],
        'restore_command_ms':restore['restore_command_ms'],
        'restored_hash_match':restore['data_constraints_indexes_rls_match'],
        'post_restore_requests':restore['summary'],'post_restore_write':restore['post_restore_write'],
        'limitations':['synthetic RSA identities, not Supabase Auth sessions',
            '30-second sampling cannot prove zero downtime',
            'manual logical restore, no PITR/roles/ACL/full Supabase services',
            'not Agent load, not saturation/capacity test, not an optimization comparison',
            'raw phase planned=360 is an estimate; global720 complete, observed split369/351, matched cycles300/300']}
    (OUT/'render-free-summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':run()
