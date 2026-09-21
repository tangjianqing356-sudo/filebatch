"""把 OSError 翻译成一句人话。

这个工具是给普通用户用的，`[Errno 30] Read-only file system: '/xxx'` 或者
`[WinError 3] 系统找不到指定的路径。` 这种东西不该出现在界面上——
用户看了既不知道发生了什么，也不知道该怎么办。

六个功能的执行循环都要做这件事，所以放在 core 里共用一份；
界面层的 `humanize()` 也走这里，保证两边说法一致。
"""
from __future__ import annotations

import errno

# errno 必须用常量不能写死数字：ENAMETOOLONG 在 Linux 是 36、macOS 是 63，
# 写死一个值会让提示在另一个平台永远不触发。
_按错误码 = {
    errno.ENOSPC: "磁盘空间不足，请清理后再试。",
    errno.ENAMETOOLONG: "文件名或路径太长了，系统存不下。请缩短前缀，或把输出文件夹换到更浅的位置。",
    errno.EROFS: "这个位置是只读的，无法写入。请换一个输出文件夹。",
    errno.EACCES: "没有权限写入这个位置，请换一个输出文件夹，或检查文件是否只读。",
    errno.ENOENT: "这个位置不存在。如果是移动硬盘或网络盘，请确认它还连着。",
    errno.ENOTDIR: "路径中有一段不是文件夹，请重新选择输出位置。",
    errno.EEXIST: "目标位置已经有同名文件了。",
    errno.ENODEV: "找不到这个设备，移动硬盘或网络盘可能已经断开。",
    errno.EXDEV: "源和目标不在同一个磁盘上，无法直接移动。请改用复制。",
}


def describe(exc: OSError) -> str:
    """一句中文说明。绝不把 errno / WinError 原文甩给用户。"""
    说法 = _按错误码.get(getattr(exc, "errno", None))
    if 说法:
        return 说法
    return "系统在读写文件时出错了。请检查磁盘空间、输出位置是否还在，以及文件是否正被其他程序占用。"
