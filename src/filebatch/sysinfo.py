"""跨平台的内存占用读取。

标准库的 resource 模块是 POSIX 专属的，Windows 上根本没有，
直接 import 会让整个命令崩掉。这里按平台分开取，不引入 psutil 这种额外依赖。
"""
from __future__ import annotations

import sys


def peak_memory_mb() -> float:
    """当前进程的峰值内存，单位 MB。取不到返回 0。"""
    if sys.platform == "win32":
        return _windows_peak_mb()
    return _posix_peak_mb()


def _posix_peak_mb() -> float:
    try:
        import resource
    except ImportError:
        return 0.0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS 的 ru_maxrss 单位是字节，Linux 是 KB
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024


def _windows_peak_mb() -> float:
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        )
        if not ok:
            return 0.0
        return counters.PeakWorkingSetSize / (1024 * 1024)
    except Exception:
        return 0.0
