import asyncio
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class AsyncTimer:
    """Schedules a callback after a calculated delay, supporting retries."""

    def __init__(
        self,
        callback: Callable[[], Awaitable[None]],
        delay_function: Callable[[int], float],
    ) -> None:
        """
        Initialize the AsyncTimer.

        Args:
            callback (Callable[[], Awaitable[None]]): The asynchronous callback to execute after the delay.
            delay_function (Callable[[int], float]): Function that calculates delay based on the number of tries.
        """
        self.callback = callback
        self.delay_function = delay_function
        self._task: Optional[asyncio.Task] = None
        self._tries: int = 0

    def reset(self) -> None:
        """Resets the timer and cancels any scheduled callback."""
        self._tries = 0
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
            logger.debug("AsyncTimer has been reset and any scheduled tasks have been cancelled.")

    def schedule(self) -> None:
        """Schedules the callback to be called after the calculated delay."""
        self._tries += 1
        delay = self.delay_function(self._tries)
        logger.debug(f"Scheduling callback to run after {delay} seconds.")
        self._task = asyncio.create_task(self._run_after_delay(delay))

    async def _run_after_delay(self, delay: float) -> None:
        """Runs the callback after the specified delay."""
        try:
            await asyncio.sleep(delay)
            await self.callback()
        except asyncio.CancelledError:
            logger.debug("AsyncTimer task was cancelled.")
        except Exception as e:
            logger.exception(f"Error in AsyncTimer callback: {e}")