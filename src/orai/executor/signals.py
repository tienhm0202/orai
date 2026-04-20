from __future__ import annotations

import signal
import threading
from types import FrameType
from typing import Optional


class ShutdownManager:
    """Cooperative shutdown: Ctrl+C sets a flag; the run loop checks it
    between tasks and exits cleanly after the current task finishes.

    A second Ctrl+C force-kills (restores original handler).
    """

    def __init__(self) -> None:
        self._shutdown_requested = threading.Event()
        self._original_sigint: Optional[signal.Handlers] = None

    def install(self) -> None:
        self._original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handler)

    def uninstall(self) -> None:
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)

    def _handler(self, signum: int, frame: Optional[FrameType]) -> None:
        if not self._shutdown_requested.is_set():
            self._shutdown_requested.set()
            import sys
            # Print immediately so user knows it was received
            print(
                "\n\033[33mCtrl+C received. Finishing current task before stopping...\033[0m",
                file=sys.stderr,
                flush=True,
            )
            # Second Ctrl+C restores default behavior (force kill)
            if self._original_sigint is not None:
                signal.signal(signal.SIGINT, self._original_sigint)

    @property
    def should_stop(self) -> bool:
        return self._shutdown_requested.is_set()
