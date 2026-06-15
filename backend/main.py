from dotenv import load_dotenv
load_dotenv()

import os
import sys
import asyncio
import selectors

# Windows psycopg SelectorEventLoop 설정 (PostgreSQL 체크포인터 필수)
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# LangSmith 명시적 설정 (.env의 LANGSMITH_TRACING 값 반영, 미설정 시 true)
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGSMITH_TRACING", "true")
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "diet-agent")
os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager
from app.api.routes.main import app
from app.core.scheduler import start_scheduler, stop_scheduler
from app.agents.graph import lifespan as graph_lifespan
import uvicorn


@asynccontextmanager
async def combined_lifespan(application):
    # graph lifespan (체크포인터 초기화) 먼저 실행
    async with graph_lifespan(application):
        # 스케줄러 시작
        start_scheduler()
        yield
        # 스케줄러 종료
        stop_scheduler()


# 기존 lifespan 덮어쓰기 대신 combined로 교체
app.router.lifespan_context = combined_lifespan

if __name__ == "__main__":
    config = uvicorn.Config(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("UVICORN_RELOAD", "false").lower() == "true",
        loop="asyncio"
    )
    server = uvicorn.Server(config)

    if sys.platform.startswith("win"):
        asyncio.run(
            server.serve(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(server.serve())
