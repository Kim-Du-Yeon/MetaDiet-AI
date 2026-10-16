"""Read-only final statistics, isolated from the shared synchronous SDK transport."""
import asyncio
import math
import logging

import httpx

from app.agents.execution_stream import emit_runtime_event, measure_stage
from app.core.config import get_settings
from app.core.external_retry import retry_external
from app.core.service_clock import service_today


_new_client = httpx.AsyncClient
_TOTAL_TIMEOUT = 15
logger = logging.getLogger(__name__)


async def read_public_stats(user_id: str | None) -> dict:
    if not user_id:
        return {}
    settings = get_settings()
    # Freeze the service date across a retry, including a midnight boundary.
    date = service_today().isoformat()

    async def read():
        # A new request-local connection pool for EACH attempt. Never reset or
        # close the process-wide Supabase client while other requests use it.
        async with _new_client(
            base_url=settings.supabase_url.rstrip('/') + '/rest/v1/',
            headers={'apikey': settings.supabase_service_key,
                     'Authorization': 'Bearer ' + settings.supabase_service_key},
            timeout=httpx.Timeout(4, connect=3, pool=1),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        ) as client:
            async with measure_stage('public_stats_meals'):
                response = await client.get('meal_logs', params={
                    'select': 'calories', 'user_id': 'eq.' + user_id, 'log_date': 'eq.' + date})
                response.raise_for_status()
                meals = response.json()
            async with measure_stage('public_stats_strategy'):
                response = await client.get('diet_strategies', params={
                    'select': 'daily_calories', 'user_id': 'eq.' + user_id,
                    'is_active': 'eq.true', 'limit': '1'})
                response.raise_for_status()
                strategy = response.json()
            if not strategy:
                return {}
            total = sum(float(row['calories']) for row in meals)
            target = float(strategy[0]['daily_calories'])
            if not math.isfinite(total) or not math.isfinite(target):
                raise ValueError('Invalid statistics')
            return {'today_calories': total, 'target_calories': target}

    try:
        # Cancellation closes the async transport; no abandoned to_thread read.
        return await asyncio.wait_for(retry_external(read, operation='public_stats'), timeout=_TOTAL_TIMEOUT)
    except TimeoutError:
        logger.warning('external_call_failure operation=public_stats error_type=TimeoutError retry=False')
        await emit_runtime_event('external_failure', operation='public_stats', error_type='TimeoutError', retry=False)
        return {}
    except Exception:
        # Unavailable is NOT zero; preserve the UI's last known values.
        return {}
