"""Compatibility entry point; generic prepare/evaluate/publish workflow."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
def approved_selection(summary):
    label=summary['selection']
    if not summary.get('judge_usage_complete'):raise ValueError('Judge usage incomplete')
    for group in summary['summary'].values():
        if group['attempts']!=100 or not group['judge_complete'] or not group['usage_complete']:raise ValueError('Incomplete comparison')
    selected=summary['summary'][label]
    if selected['fresh_percent']!=100 or selected['no_write_percent']!=100 or selected['failure_percent']>2:raise ValueError('Safety/freshness gate failed')
    if label=='v2' and not summary['candidate_passed']:raise ValueError('Candidate gate failed')
    return label

from scripts.prompt_release_workflow import main
if __name__=='__main__':main()
