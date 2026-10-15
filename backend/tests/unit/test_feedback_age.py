from datetime import datetime, timedelta, timezone
import pytest
from app.db.admin_feedback import feedback_is_stale


@pytest.mark.parametrize('status,seconds,expected', [
    ('received', 7*86400, True), ('reproducing',7*86400+1,True),
    ('on_hold',8*86400,True), ('received',7*86400-1,False),
    ('fixed',30*86400,False), ('resolved',30*86400,False),
    ('received',-60,False)])
def test_old_pending_boundary_uses_server_time(status,seconds,expected):
    now=datetime(2026,10,15,0,0,tzinfo=timezone.utc)
    assert feedback_is_stale({'status':status,'created_at':now-timedelta(seconds=seconds)},now)==expected
