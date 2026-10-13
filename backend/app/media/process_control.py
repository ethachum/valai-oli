"""
Process suspension and resumption utilities for Windows and POSIX.
Allows pausing and resuming active download/conversion subprocesses.
"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


def suspend_process(pid: int) -> bool:
    """Suspend execution of a process by PID."""
    try:
        if sys.platform == "win32":
            import ctypes
            # PROCESS_SUSPEND_RESUME = 0x0800
            handle = ctypes.windll.kernel32.OpenProcess(0x0800, False, pid)
            if not handle:
                logger.warning("Could not open process %d for suspend", pid)
                return False
            try:
                status = ctypes.windll.ntdll.NtSuspendProcess(handle)
                return status == 0
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        else:
            import os
            import signal
            os.kill(pid, signal.SIGSTOP)
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to suspend process %d: %s", pid, exc)
        return False


def resume_process(pid: int) -> bool:
    """Resume execution of a suspended process by PID."""
    try:
        if sys.platform == "win32":
            import ctypes
            # PROCESS_SUSPEND_RESUME = 0x0800
            handle = ctypes.windll.kernel32.OpenProcess(0x0800, False, pid)
            if not handle:
                logger.warning("Could not open process %d for resume", pid)
                return False
            try:
                status = ctypes.windll.ntdll.NtResumeProcess(handle)
                return status == 0
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        else:
            import os
            import signal
            os.kill(pid, signal.SIGCONT)
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to resume process %d: %s", pid, exc)
        return False
