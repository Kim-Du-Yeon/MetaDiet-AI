"""Cross-process serialization of checkpoint mutations for a conversation."""
import json
import logging
import time
from contextlib import asynccontextmanager
from app.db.proposals import connection


class AccountUnavailable(PermissionError):
    """The account disappeared while a request waited for its execution lock."""


@asynccontextmanager
async def conversation_lock(user_id: str, thread_id: str):
    async with connection() as conn:
        # Shared account lock lets conversations for the same user run normally,
        # while account deletion takes the matching exclusive lock.
        await conn.execute(
            "select pg_advisory_xact_lock_shared(hashtextextended(%s,0))",
            (f"account:{user_id}",),
        )
        account = await (
            await conn.execute("select id from users where id=%s", (user_id,))
        ).fetchone()
        if not account:
            raise AccountUnavailable("account_unavailable")
        await conn.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"conversation:{user_id}:{thread_id}",),
        )
        yield


async def serialized_stream(factory, user_id: str, thread_id: str):
    started = time.perf_counter()
    yield 'data: ' + json.dumps({'type': 'progress', 'phase': 'conversation_wait',
        'label': '요청을 받았어요. 대화 실행 순서를 확인 중입니다.'}, ensure_ascii=False) + '\n\n'
    try:
        async with conversation_lock(user_id, thread_id):
            logging.getLogger(__name__).warning('chat_preparation stage=conversation_lock elapsed_ms=%.3f',
                (time.perf_counter() - started) * 1000)
            yield 'data: ' + json.dumps({'type': 'progress', 'phase': 'checkpoint_restore',
                'label': '저장된 대화 상태를 확인 중입니다.'}, ensure_ascii=False) + '\n\n'
            async for event in factory():
                yield event
    except Exception:
        yield "data: " + json.dumps({"type": "error", "content": "대화 처리 또는 연결에 실패했습니다. 잠시 후 다시 시도해주세요."}, ensure_ascii=False) + "\n\n"
