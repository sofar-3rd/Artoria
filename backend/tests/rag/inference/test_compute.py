import asyncio
import threading
import time

import pytest

from app.rag.inference.compute import run_cpu


async def test_run_cpu_uses_a_single_worker_thread_and_propagates_errors():
    names = {await run_cpu(lambda: threading.current_thread().name) for _ in range(3)}
    assert len(names) == 1 and next(iter(names)) != threading.current_thread().name
    with pytest.raises(ZeroDivisionError):
        await run_cpu(lambda: 1 / 0)


async def test_calls_never_run_in_parallel():
    """Several torch calls at once only fight for the cores: everything queues on one thread."""
    running, peak = 0, 0
    guard = threading.Lock()

    def work():
        nonlocal running, peak
        with guard:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with guard:
            running -= 1
        return True

    assert all(await asyncio.gather(*(run_cpu(work) for _ in range(6))))
    assert peak == 1


async def test_the_event_loop_stays_responsive_while_inference_runs():
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(heartbeat())
    await run_cpu(time.sleep, 0.3)
    task.cancel()
    assert ticks >= 15  # a blocked loop would have produced almost none


async def test_arguments_are_passed_through():
    assert await run_cpu(lambda a, b: a * b, 6, 7) == 42
