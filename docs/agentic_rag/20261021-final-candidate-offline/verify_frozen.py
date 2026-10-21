"""Offline-only integrity check. No application imports, provider calls or writes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
manifest = json.loads(Path(__file__).with_name('manifest.json').read_text(encoding='utf-8'))
for name, expected in manifest['files'].items():
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, name
ledger = ROOT/'tmp/eval-budget.sqlite'
assert hashlib.sha256(ledger.read_bytes()).hexdigest() == manifest['budget']['ledger_sha256'], 'budget ledger changed'
print('Frozen sources, saved results and unchanged budget ledger verified; no provider calls.')
