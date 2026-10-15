"""Private feedback review, reached only after server administrator authorization."""
from typing import Literal
from uuid import UUID
from app.core.config import get_settings
from app.db.proposals import connection
from app.db.feedback import FeedbackStorageUnavailable

FeedbackStatus = Literal['received', 'reproducing', 'fixed', 'resolved', 'on_hold']
SUMMARY = 'id, rating, category, left(comment, 100) as preview, status, version, created_at, updated_at, assignee_id'
DETAIL = 'id, rating, category, comment, status, version, admin_note, created_at, updated_at, assignee_id'
UNSET = object()


class InvalidAssignee(ValueError):
    pass


def admin_emails():
    return [email.strip().lower() for email in get_settings().admin_emails.split(',') if email.strip()]


def public(row):
    return {key: value.isoformat() if hasattr(value, 'isoformat') else str(value) if isinstance(value, UUID) else value
            for key, value in row.items()}


class AdminFeedbackRepository:
    def __init__(self, connect=connection):
        self.connect = connect

    async def list(self, *, status=None, category=None, assignee=None, limit=20, offset=0):
        clauses, params = [], []
        for field, value in (('status', status), ('category', category)):
            if value is not None:
                clauses.append(field + '=%s')
                params.append(value)
        if assignee == 'unassigned':
            clauses.append('assignee_id is null')
        elif assignee is not None:
            clauses.append('assignee_id=%s')
            params.append(assignee)
        where = ' where ' + ' and '.join(clauses) if clauses else ''
        # Pending counts follow assignee/category, independently of the status filter.
        pending_clauses, pending_params = [], []
        if category is not None:
            pending_clauses.append('category=%s'); pending_params.append(category)
        if assignee == 'unassigned':
            pending_clauses.append('assignee_id is null')
        elif assignee is not None:
            pending_clauses.append('assignee_id=%s'); pending_params.append(assignee)
        pending_scope = ' and '.join(pending_clauses) or 'true'
        matched_scope = ' and '.join(clauses) or 'true'
        try:
            async with self.connect() as conn:
                await conn.execute('set transaction isolation level repeatable read, read only')
                rows = await (await conn.execute(
                    f'select {SUMMARY} from beta_feedback{where} order by created_at desc, id desc limit %s offset %s',
                    (*params, limit + 1, offset))).fetchall()
                counts = await (await conn.execute(
                    f'''select count(*) filter(where status in ('received','reproducing','on_hold')) as total_unprocessed,
                        count(*) filter(where status in ('received','reproducing','on_hold') and {pending_scope}) as unprocessed,
                        count(*) filter(where {matched_scope}) as matched_total from beta_feedback''',
                    (*pending_params,*params))).fetchone()
                return {'items': [public(row) for row in rows[:limit]], 'has_more': len(rows) > limit,
                        'counts': counts}
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

    async def assignees(self):
        try:
            async with self.connect() as conn:
                rows = await (await conn.execute(
                    'select id, email from auth.users where lower(email)=any(%s) and email_confirmed_at is not null order by email',
                    (admin_emails(),))).fetchall()
                return {'items': [public(row) for row in rows]}
        except Exception:
            raise FeedbackStorageUnavailable('담당자 목록을 불러오지 못했습니다.') from None

    async def history(self, feedback_id, *, limit=20, before_version=None):
        try:
            async with self.connect() as conn:
                exists = await (await conn.execute('select id from beta_feedback where id=%s', (feedback_id,))).fetchone()
                if not exists:
                    return None
                rows = await (await conn.execute(
                    '''select h.*, a.email as actor_email, b.email as before_assignee_email,
                        c.email as after_assignee_email from beta_feedback_history h
                        left join auth.users a on a.id=h.actor_auth_id
                        left join auth.users b on b.id=h.before_assignee_id
                        left join auth.users c on c.id=h.after_assignee_id
                        where h.feedback_id=%s and (%s::integer is null or h.version<%s)
                        order by h.version desc limit %s''',
                    (feedback_id, before_version, before_version, limit+1))).fetchall()
                items = [public(row) for row in rows[:limit]]
                return {'items': items, 'has_more': len(rows)>limit,
                        'next_before_version': items[-1]['version'] if len(rows)>limit else None}
        except Exception:
            raise FeedbackStorageUnavailable('변경 이력을 불러오지 못했습니다.') from None

    async def update(self, feedback_id, *, version, status, admin_note, admin_auth_id, assignee_id=UNSET):
        try:
            async with self.connect() as conn:
                old = await (await conn.execute(
                    'select status, admin_note, assignee_id from beta_feedback where id=%s and version=%s for update',
                    (feedback_id, version))).fetchone()
                if not old:
                    return None
                assigned = old['assignee_id'] if assignee_id is UNSET else assignee_id
                if assigned is not None and assignee_id is not UNSET:
                    eligible = await (await conn.execute(
                        'select id from auth.users where id=%s and lower(email)=any(%s) and email_confirmed_at is not null',
                        (assigned, admin_emails()))).fetchone()
                    if not eligible:
                        raise InvalidAssignee('허용된 관리자만 담당자로 지정할 수 있습니다.')
                row = await (await conn.execute(
                    f'''update beta_feedback set status=%s, admin_note=%s, assignee_id=%s, updated_by=%s,
                        updated_at=now(), version=version+1 where id=%s and version=%s returning {DETAIL}''',
                    (status, admin_note, assigned, admin_auth_id, feedback_id, version))).fetchone()
                await conn.execute(
                    '''insert into beta_feedback_history (feedback_id,version,actor_auth_id,
                        before_status,after_status,before_note,after_note,before_assignee_id,after_assignee_id)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (feedback_id,row['version'],admin_auth_id,old['status'],status,old['admin_note'],admin_note,
                     old['assignee_id'],assigned))
                return public(row)
        except InvalidAssignee:
            raise
        except Exception:
            raise FeedbackStorageUnavailable('피드백 처리를 저장하지 못했습니다.') from None
