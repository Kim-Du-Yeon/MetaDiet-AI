from datetime import date

from app.agents.goal_manager.node import (
    _calc_goal_progress,
    _calc_needed_weekly_rate,
    _calc_weekly_rate,
)


def test_progress_pct_halfway():
    r = _calc_goal_progress(current_weight=70, target_weight=65, start_weight=75)
    assert r["progress_pct"] == 50.0
    assert r["remaining_weight"] == 5.0


def test_progress_pct_goal_exceeded():
    r = _calc_goal_progress(current_weight=63, target_weight=65, start_weight=75)
    assert r["progress_pct"] == 120.0
    assert r["remaining_weight"] == -2.0


def test_progress_pct_not_started_yet():
    r = _calc_goal_progress(current_weight=75, target_weight=65, start_weight=75)
    assert r["progress_pct"] == 0.0


def test_progress_pct_target_equals_start_is_100():
    r = _calc_goal_progress(current_weight=75, target_weight=75, start_weight=75)
    assert r["progress_pct"] == 100.0


def test_progress_pct_bulk_direction():
    # 증량: target > start. 부호가 뒤집혀도 같은 공식으로 진행률이 맞아야 함.
    r = _calc_goal_progress(current_weight=68, target_weight=75, start_weight=65)
    assert r["progress_pct"] == 30.0


def test_weekly_rate_loss():
    rate = _calc_weekly_rate(current_weight=70, current_date="2026-06-15", prev_weight=72, prev_date="2026-06-01")
    assert rate == -1.0


def test_weekly_rate_gain():
    rate = _calc_weekly_rate(current_weight=72, current_date="2026-06-15", prev_weight=70, prev_date="2026-06-01")
    assert rate == 1.0


def test_weekly_rate_same_day_returns_none():
    rate = _calc_weekly_rate(current_weight=70, current_date="2026-06-01", prev_weight=72, prev_date="2026-06-01")
    assert rate is None


def test_needed_weekly_rate_matches_formula():
    today = date(2026, 6, 19)
    rate = _calc_needed_weekly_rate(remaining_weight=5, target_date_str="2026-09-01", today=today)
    days_remaining = (date(2026, 9, 1) - today).days
    assert rate == round(5 / (days_remaining / 7), 2)


def test_needed_weekly_rate_past_deadline_returns_none():
    today = date(2026, 6, 19)
    rate = _calc_needed_weekly_rate(remaining_weight=5, target_date_str="2026-01-01", today=today)
    assert rate is None


def test_needed_weekly_rate_today_is_deadline_returns_none():
    today = date(2026, 6, 19)
    rate = _calc_needed_weekly_rate(remaining_weight=5, target_date_str="2026-06-19", today=today)
    assert rate is None
