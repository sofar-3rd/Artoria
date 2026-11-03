from app.db import SessionLocal, engine
from app.models import DEFAULT_TITLE, Thread


async def test_threads_table_roundtrip():
    try:
        async with SessionLocal() as session:
            thread = Thread()
            session.add(thread)
            await session.commit()
            got = await session.get(Thread, thread.id)
            assert got is not None
            assert got.title == DEFAULT_TITLE
            assert got.created_at is not None
            await session.delete(got)
            await session.commit()
    finally:
        await engine.dispose()
