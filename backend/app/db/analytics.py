"""Privacy-minimal product analytics persistence and aggregate reporting."""

from dataclasses import dataclass, field
import json
from typing import Literal
from uuid import UUID

from app.db.proposals import connection


EventName = Literal[
    "signup_completed", "onboarding_started", "onboarding_completed",
    "chat_sent", "chat_completed", "meal_proposed", "meal_confirmed",
    "measurement_confirmed", "feedback_submitted", "error_shown",
]
EventStatus = Literal["success", "failed", "cancelled"]


@dataclass(frozen=True)
class ProductEventInput:
    event_name: EventName
    status: EventStatus
    client_event_id: UUID
    session_id: UUID
    duration_ms: int | None = None
    trace_id: str | None = None
    properties: dict = field(default_factory=dict)


class ProductAnalyticsUnavailable(RuntimeError):
    """Stable public error without database or event payload details."""


class ProductEventRepository:
    def __init__(self, connect=connection):
        self.connect = connect

    async def record(self, user_id: str, event: ProductEventInput) -> tuple[dict, bool]:
        try:
            async with self.connect() as conn:
                inserted = await (
                    await conn.execute(
                        """insert into product_events
                           (user_id, event_name, status, client_event_id, session_id,
                            duration_ms, trace_id, properties)
                           values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                           on conflict (user_id, client_event_id) do nothing
                           returning id""",
                        (
                            user_id, event.event_name, event.status, event.client_event_id,
                            event.session_id, event.duration_ms, event.trace_id,
                            json.dumps(event.properties, ensure_ascii=False, separators=(",", ":")),
                        ),
                    )
                ).fetchone()
                if inserted:
                    return {"id": str(inserted["id"])}, True
                existing = await (
                    await conn.execute(
                        "select id from product_events where user_id=%s and client_event_id=%s",
                        (user_id, event.client_event_id),
                    )
                ).fetchone()
                if not existing:
                    raise RuntimeError("event conflict lookup returned no row")
                return {"id": str(existing["id"])}, False
        except ProductAnalyticsUnavailable:
            raise
        except Exception as exc:
            raise ProductAnalyticsUnavailable("제품 분석 이벤트를 저장할 수 없습니다.") from exc

    async def overview(self, days: int = 7) -> dict:
        try:
            async with self.connect() as conn:
                row = await (
                    await conn.execute(
                        """select
                           count(distinct user_id) filter (where created_at >= now() - interval '1 day') as dau,
                           count(distinct user_id) filter (where created_at >= now() - interval '7 days') as wau,
                           count(distinct user_id) filter (where event_name='signup_completed') as signups,
                           count(distinct user_id) filter (where event_name='onboarding_completed' and status='success') as onboarding_completed,
                           count(distinct user_id) filter (where event_name='meal_confirmed' and status='success') as first_meal_users,
                           count(*) filter (where event_name='chat_completed') as chat_total,
                           count(*) filter (where event_name='chat_completed' and status='success') as chat_succeeded,
                           percentile_cont(0.5) within group (order by duration_ms)
                               filter (where event_name='chat_completed' and duration_ms is not null) as latency_p50_ms,
                           percentile_cont(0.95) within group (order by duration_ms)
                               filter (where event_name='chat_completed' and duration_ms is not null) as latency_p95_ms,
                           count(*) filter (where status='failed') as errors
                           from product_events
                           where created_at >= now() - (%s * interval '1 day')""",
                        (days,),
                    )
                ).fetchone() or {}
        except Exception as exc:
            raise ProductAnalyticsUnavailable("제품 분석 지표를 불러올 수 없습니다.") from exc

        def number(name: str) -> int:
            return int(row.get(name) or 0)

        def rate(part: int, total: int) -> float:
            return round(part / total, 4) if total else 0.0

        signups = number("signups")
        chats = number("chat_total")
        return {
            "window_days": days,
            "active_users": {"daily": number("dau"), "weekly": number("wau")},
            "funnel": {
                "signups": signups,
                "onboarding_completed": number("onboarding_completed"),
                "first_meal_users": number("first_meal_users"),
                "onboarding_rate": rate(number("onboarding_completed"), signups),
                "first_meal_rate": rate(number("first_meal_users"), signups),
            },
            "agent": {
                "requests": chats,
                "succeeded": number("chat_succeeded"),
                "success_rate": rate(number("chat_succeeded"), chats),
                "latency_p50_ms": number("latency_p50_ms"),
                "latency_p95_ms": number("latency_p95_ms"),
                "errors": number("errors"),
            },
        }
