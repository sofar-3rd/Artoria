import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agent import build_agent, build_chat_model
from app.chat_stream import drain_wrap_ups
from app.config import settings
from app.db import engine
from app.rag.bootstrap import Rag, build_rag, warm_up
from app.rag.interfaces.tools import build_kb_tools
from app.routers import chat, kb, threads

logger = logging.getLogger(__name__)


def create_app(model: BaseChatModel | None = None, rag: Rag | None = None) -> FastAPI:
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
            active_rag = rag if rag is not None else (build_rag() if settings.rag_enabled else None)
            app.state.rag = active_rag
            if active_rag is not None and settings.rag_load_on_start:
                started = time.monotonic()
                await warm_up(active_rag)
                logger.warning("rag models loaded in %.0f s", time.monotonic() - started)
            app.state.sync_tasks = set()
            app.state.sync_running = set()
            kb_tools = (
                build_kb_tools(active_rag.catalog, active_rag.searcher, settings.rag_top_k)
                if active_rag is not None
                else []
            )
            app.state.agent = build_agent(model or build_chat_model(), checkpointer, kb_tools)
            yield
        finally:
            await drain_wrap_ups()
            await kb.drain_syncs(app)
            await pool.close()
            await engine.dispose()

    app = FastAPI(title="sagent", lifespan=lifespan)
    app.include_router(threads.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(kb.router, prefix="/api")
    return app


app = create_app()
