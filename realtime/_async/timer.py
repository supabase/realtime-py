import asyncio
from typing import Callable


class AsyncTimer:
    def __init__(self, callback: Callable, timer_calc: Callable[[int], int]):
        self.callback = callback
        self.timer_calc = timer_calc
        self.timer = None
        self.tries = 0

    def reset(self):
        self.tries = 0
        if self.timer:
            self.timer.cancel()

    def schedule_timeout(self):
        if self.timer:
            self.timer.cancel()

        self.timer = asyncio.create_task(self._run_timer())

    async def _run_timer(self):
        await asyncio.sleep(self.timer_calc(self.tries + 1))
        self.tries += 1
        await self.callback()
