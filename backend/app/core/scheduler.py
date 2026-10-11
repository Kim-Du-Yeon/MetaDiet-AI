from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date
from app.core.service_clock import service_today

scheduler = AsyncIOScheduler()


async def send_inbody_reminders():
    from app.db.supabase_client import get_supabase
    sb = get_supabase()
    users = sb.table("users").select("id").execute().data
    for user in users:
        uid = user["id"]
        rows = sb.table("inbody_logs") \
            .select("measured_date") \
            .eq("user_id", uid) \
            .order("measured_date", desc=True) \
            .limit(1) \
            .execute().data
        needs_reminder = False
        if not rows:
            needs_reminder = True
        else:
            last = date.fromisoformat(rows[0]["measured_date"])
            if (service_today() - last).days >= 21:
                needs_reminder = True
        if needs_reminder:
            sb.table("chat_history").insert({
                "user_id": uid,
                "thread_id": "reminders",
                "role": "assistant",
                "content": "인바디를 측정한 지 3주가 지났어요! 인바디 사진을 업로드해주세요.",
                "agent_type": "reminder"
            }).execute()


def start_scheduler():
    scheduler.add_job(
        send_inbody_reminders,
        CronTrigger(hour=9, minute=0),
        id="inbody_reminder",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown()
