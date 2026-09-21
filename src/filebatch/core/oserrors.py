"""把 OSError 翻译成一句人话。

这个工具是给普通用户用的，`[Errno 30] Read-only file system: '/xxx'` 或者
`[WinError 3] 系统找不到指定的路径。` 这种东西不该出现在界面上——
用户看了既不知道发生了什么，也不知道该怎么办。

六个功能的执行循环都要做这件事，所以放在 core 里共用一份；
界面层的 `humanize()` 也走这里，保证两边说法一致。
"""
from __future__ import annotations

import errno
import sys

# errno 必须用常量不能写死数字：ENAMETOOLONG 在 Linux 是 36、macOS 是 63，
# 写死一个值会让提示在另一个平台永远不触发。
_按错误码 = {
    errno.ENOSPC: "磁盘空间不足，请清理后再试。",
    errno.ENAMETOOLONG: "文件名或路径太长了，系统存不下。请缩短前缀，或把输出文件夹换到更浅的位置。",
    errno.EROFS: "这个位置是只读的，无法写入。请换一个输出文件夹。",
    errno.EACCES: "没有权限写入这个位置，请换一个输出文件夹，或检查文件是否只读。",
    # ENOENT 有两种情况：源文件没了、或者输出位置没了。
    # 这里是前者；后者由 describe() 里的 位置问题 分支单独给话术。
    errno.ENOENT: "找不到这个文件，它可能已经被移动、重命名或删除了。",
    errno.ENOTDIR: "路径中有一段不是文件夹，请重新选择输出位置。",
    errno.EEXIST: "目标位置已经有同名文件了。",
    errno.ENODEV: "找不到这个设备，移动硬盘或网络盘可能已经断开。",
    errno.EXDEV: "源和目标不在同一个磁盘上，无法直接移动。请改用复制。",
}


# Windows 的错误码和 POSIX errno 对不上：同一件事 Windows 会给
# winerror 206（文件名超长）而 errno 只是个笼统的 22。
# Windows CI 上"超长文件名"那条用例就是因为只看 errno 而掉进了兜底文案。
_按WINDOWS错误码 = {
    2: "找不到这个文件，它可能已经被移动、重命名或删除了。",
    3: "这个路径不存在。如果是移动硬盘或网络盘，请确认它还连着。",
    5: "没有权限写入这个位置，请换一个输出文件夹，或检查文件是否只读。",
    15: "找不到这个盘符，移动硬盘或网络盘可能已经断开。",
    32: "这个文件正被其他程序占用（多半是还开在 Excel 里），请关掉它再试。",
    33: "文件的一部分被其他程序锁住了，请关掉正在用它的程序再试。",
    112: "磁盘空间不足，请清理后再试。",
    123: "文件名里有系统不允许的字符，或者名字太长了。请换个名字。",
    206: "文件名或路径太长了，系统存不下。请缩短前缀，或把输出文件夹换到更浅的位置。",
}

# Windows 上文件名太长 / 含非法字符，errno 经常只给一个笼统的 EINVAL。
# POSIX 上 EINVAL 的含义不一样，所以这条只在 Windows 生效。
_WINDOWS的EINVAL = (
    "文件名或路径不被系统接受，多半是太长了，也可能含有不允许的字符。"
    "请缩短前缀，或把输出文件夹换到更浅的位置。"
)


def describe(exc: OSError, source=None) -> str:
    """一句中文说明。绝不把 errno / WinError 原文甩给用户。

    :param source: 正在处理的源文件。给了的话就能分清
        "源文件没了"和"输出位置没了"——Windows CI 上实测，
        输出指向一个不存在的盘符时，用户看到的是
        "文件已不存在，可能在处理过程中被移动或删除"，
        矛头指错了地方。
    """
    出错的 = getattr(exc, "filename", None)
    位置问题 = (
        source is not None
        and 出错的 is not None
        and str(出错的) != str(source)
    )

    win = getattr(exc, "winerror", None)
    if win is not None:
        if 位置问题 and win in (2, 3, 15):
            return "输出位置不存在或已经不可用。如果是移动硬盘或网络盘，请确认它还连着。"
        说法 = _按WINDOWS错误码.get(win)
        if 说法:
            return 说法

    code = getattr(exc, "errno", None)
    if 位置问题 and code in (errno.ENOENT, errno.ENOTDIR):
        return "输出位置不存在或已经不可用。如果是移动硬盘或网络盘，请确认它还连着。"

    说法 = _按错误码.get(code)
    if 说法:
        return 说法

    if sys.platform == "win32" and code == errno.EINVAL:
        return _WINDOWS的EINVAL

    return "系统在读写文件时出错了。请检查磁盘空间、输出位置是否还在，以及文件是否正被其他程序占用。"
