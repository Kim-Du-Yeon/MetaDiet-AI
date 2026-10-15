"""Private feedback review, reached only after server administrator authorization."""
from typing import Literal
from app.db.proposals import connection
from app.db.feedback import FeedbackStorageUnavailable

FeedbackStatus = Literal['received', 'reproducing', 'fixed', 'resolved', 'on_hold']
SUMMARY = 'id, rating, category, left(comment, 100) as preview, status, version, created_at, updated_at'
DETAIL = 'id, rating, category, comment, status, version, admin_note, created_at, updated_at'


def public(row):
    return {key: value.isoformat() if hasattr(value, 'isoformat') else str(value) if key == 'id' else value
            for key, value in row.items()}


class AdminFeedbackRepository:
    def __init__(self, connect=connection):
        self.connect = connect

    async def list(self, *, status=None, category=None, limit=20, offset=0):
        clauses, params = [], []
        for field, value in (('status', status), ('category', category)):
            if value is not None:
                clauses.append(field + '=%s')
                params.append(value)
        where = ' where ' + ' and '.join(clauses) if clauses else ''
        try:
            async with self.connect() as conn:
                rows = await (await conn.execute(
                    f'select {SUMMARY} from beta_feedback{where} order by created_at desc, id desc limit %s offset %s',
                    (*params, limit + 1, offset))).fetchall()
                return {'items': [public(row) for row in rows[:limit]], 'has_more': len(rows) > limit}
        except Exception:
            raise FeedbackStorageUnavailable('피드백 목록을 불러오지 못했습니다.') from None

    async def get(self, feedback_id):
        try:
            async with self.connect() as conn:
                row = await (await conn.execute(f'select {DETAIL} from beta_feedback where id=%s',
                                               (feedback_id,))).fetchone()
                return public(row) if row else None
        except Exception:
            raise FeedbackStorageUnavailable('피드백을 불러오지 못했습니다.') from None

    async def update(self, feedback_id, *, version, status, admin_note, admin_auth_id):
        try:
            async with self.connect() as conn:
                row = await (await conn.execute(
                    f'''update beta_feedback set status=%s, admin_note=%s, updated_by=%s,
                        updated_at=now(), version=version+1 where id=%s and version=%s returning {DETAIL}''',
                    (status, admin_note, admin_auth_id, feedback_id, version))).fetchone()
                return public(row) if row else None
        except Exception:
            raise FeedbackStorageUnavailable('피드백 처리를 저장하지 못했습니다.') from None
