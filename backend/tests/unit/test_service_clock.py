from datetime import datetime, timezone


def test_service_today_uses_configured_timezone_across_utc_midnight():
    from app.core.service_clock import service_today

    utc_evening = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)

    assert service_today(utc_evening, timezone_name="Asia/Seoul").isoformat() == "2026-10-11"
