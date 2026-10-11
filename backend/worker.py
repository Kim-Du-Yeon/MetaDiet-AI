"""Dedicated scheduler worker; API replicas must not run duplicate cron jobs."""
import asyncio
import signal

from dotenv import load_dotenv

load_dotenv()

from app.core.scheduler import start_scheduler, stop_scheduler


async def run() -> None:
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stopped.set)
        except NotImplementedError:  # Windows local smoke only.
            pass
    start_scheduler()
    try:
        await stopped.wait()
    finally:
        stop_scheduler()


if __name__ == "__main__":
    asyncio.run(run())
