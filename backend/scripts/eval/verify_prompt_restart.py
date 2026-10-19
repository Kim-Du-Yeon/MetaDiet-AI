"""Local restart/rollback drill with synthetic releases and no API/DB calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))


def child(release_root):
    from app.core import prompts
    prompts.RELEASE_ROOT = release_root
    from app.agents.team import BASE_INSTRUCTION
    metadata = prompts.prompt_metadata()
    assert BASE_INSTRUCTION == prompts.get_prompt('team.base')
    return {**metadata, 'effective_system_sha256': hashlib.sha256(BASE_INSTRUCTION.encode()).hexdigest()}


def verify_restart(workspace):
    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=workspace) as folder:
        release_root = Path(folder)
        baseline = json.loads((ROOT / 'backend/app/prompts/releases/v1.json').read_text(encoding='utf-8'))
        (release_root / 'v1.json').write_text(json.dumps(baseline), encoding='utf-8')
        candidate = json.loads(json.dumps(baseline))
        candidate['release'] = 'v2'
        entry = candidate['prompts']['team.base']
        entry['text'] += '\nSynthetic restart drill only.'
        entry['version'] = '1.0.1'
        entry['sha256'] = hashlib.sha256(entry['text'].encode()).hexdigest()
        (release_root / 'v2.json').write_text(json.dumps(candidate), encoding='utf-8')
        # Do not inherit real keys or load repository dotenv files in children.
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'TEMP', 'TMP') if key in os.environ}
        env.update(SUPABASE_URL='https://synthetic.invalid', SUPABASE_SERVICE_KEY='synthetic-only',
                   SUPABASE_JWT_SECRET='synthetic-only', PINECONE_API_KEY='synthetic-only',
                   LANGSMITH_TRACING='false', PYTHONIOENCODING='utf-8')
        steps = []
        for release in ('v1', 'v2', 'v1', 'v999'):
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                '--child', '--release-root', str(release_root)],
                cwd=release_root, env={**env, 'PROMPT_RELEASE': release},
                capture_output=True, text=True, encoding='utf-8', timeout=45)
            step = {'release': release, 'returncode': result.returncode}
            if result.returncode == 0:
                step.update(json.loads(result.stdout))
            else:
                step['error_type'] = 'release_rejected' if result.returncode == 2 else 'child_failed'
            steps.append(step)
    first, changed, restored, invalid = steps
    passed = (all(step['returncode'] == 0 for step in steps[:3]) and invalid['returncode'] == 2
              and first.get('prompt_bundle_sha256') == restored.get('prompt_bundle_sha256')
              and first.get('effective_system_sha256') == restored.get('effective_system_sha256')
              and changed.get('effective_system_sha256') != first.get('effective_system_sha256'))
    return {'scope': 'local_isolated_processes_not_render_deployment',
            'v2_is_temporary_fixture': True, 'real_credentials_inherited': False,
            'passed': passed, 'steps': steps}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--release-root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.child:
        try:
            print(json.dumps(child(args.release_root)))
        except ValueError:
            raise SystemExit(2)
        return
    if args.output is None:
        parser.error('--output is required')
    if args.output.exists():
        raise SystemExit('Refusing to overwrite evidence')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = verify_restart(args.output.parent)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
