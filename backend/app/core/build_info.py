"""Public, allowlisted release identity. Never expose host IDs or environment dumps."""
import os
import re


def build_info():
    commit = os.getenv('RENDER_GIT_COMMIT', os.getenv('APP_BUILD_COMMIT', ''))
    return {'commit': commit if re.fullmatch(r'[0-9a-fA-F]{7,40}', commit) else 'unknown',
            'protocol': 2, 'delivery': 'verified_buffered'}
