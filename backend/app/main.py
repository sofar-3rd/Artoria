from contextlib import asynccontextmanager

from fastapi import FastAPI
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agent import build_agent, build_chat_model
from app.config import settings
from app.db import engine
from app.routers import chat, threads


def create_app(model: BaseChatModel | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool = AsyncConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=settings.db_pool_max,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            open=False,
        )
        await pool.open(wait=True)
        try:
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
            app.state.checkpointer = checkpointer
            app.state.agent = build_agent(model or build_chat_model(), checkpointer)
            yield
        finally:
            await pool.close()
            await engine.dispose()

    app = FastAPI(title="sagent", lifespan=lifespan)
    app.include_router(threads.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    return app


app = create_app()
