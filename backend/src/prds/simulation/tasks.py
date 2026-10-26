"""Single-process task ownership and structured cancellation."""
import asyncio
from collections.abc import Awaitable


async def gather_owned(*coroutines):
    """A failing sibling must not leave other calls running in the background."""
    tasks = [asyncio.ensure_future(coro) for coro in coroutines]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


class SimulationTaskManager:
    def __init__(self):
        self.shutting_down = False
        self.tasks: dict[str, asyncio.Task] = {}

    def start(self, run_id: str, work: Awaitable) -> None:
        task = asyncio.create_task(work, name=f"simulation:{run_id}")
        self.tasks[run_id] = task
        def finished(done):
            if self.tasks.get(run_id) is done:
                self.tasks.pop(run_id, None)
            if not done.cancelled():
                done.exception()  # retrieve unexpected errors as well
        task.add_done_callback(finished)

    async def cancel(self, run_id: str, timeout: float = 10.0) -> bool:
        task = self.tasks.get(run_id)
        if task is None or task.done():
            return True
        task.cancel()
        done, _ = await asyncio.wait([task], timeout=timeout)
        return bool(done)

    async def shutdown(self):
        self.shutting_down = True
        for task in list(self.tasks.values()):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)


_manager = SimulationTaskManager()


def get_tasks() -> SimulationTaskManager:
    return _manager
