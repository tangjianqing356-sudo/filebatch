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
    """Windows 下的峰值工作集。

    两个坑（Windows CI 上实测返回 0 才发现的）：

    1. `GetCurrentProcess` 不声明 restype 的话，ctypes 按 C int 处理，
       64 位下伪句柄 (HANDLE)-1 会被截断，传回去 API 直接失败；
    2. `GetProcessMemoryInfo` 不声明 argtypes 的话，指针参数同样可能被截断。

    另外这个函数在 Windows 7 之后搬进了 kernel32（K32 前缀），
    老系统还留在 psapi 里，两个都试一遍。
    """
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

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []

        取内存 = None
        for 库, 函数名 in ((kernel32, "K32GetProcessMemoryInfo"),
                          (None, "GetProcessMemoryInfo")):
            try:
                if 库 is None:
                    库 = ctypes.WinDLL("psapi", use_last_error=True)
                取内存 = getattr(库, 函数名)
                break
            except (OSError, AttributeError):
                continue
        if 取内存 is None:
            return 0.0

        取内存.restype = wintypes.BOOL
        取内存.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if not 取内存(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return 0.0
        return counters.PeakWorkingSetSize / (1024 * 1024)
    except Exception:
        return 0.0
