"""把技术异常翻译成普通人能看懂的话。

原则：弹窗里只说人话，技术细节（异常类型、errno、堆栈）留在详细日志里。
用户看到 "PermissionError: [Errno 13]" 只会困惑，看到"文件可能正被其他程序打开"才知道该干什么。
"""
from __future__ import annotations


def humanize(exc: BaseException) -> str:
    """异常 -> 一句人话。"""
    if isinstance(exc, PermissionError):
        return "这个文件无法访问，可能正在被其他程序打开，或者当前文件夹没有写入权限。"
    if isinstance(exc, FileNotFoundError):
        return "找不到这个文件，它可能已经被移动、重命名或删除了。"
    if isinstance(exc, IsADirectoryError):
        return "这是一个文件夹，不是文件。"
    if isinstance(exc, NotADirectoryError):
        return "指定的路径不是文件夹。"
    if isinstance(exc, FileExistsError):
        return "目标位置已经有同名文件了。"
    if isinstance(exc, UnicodeDecodeError):
        return "这个文件的编码无法识别，可能不是文本文件。"
    if isinstance(exc, MemoryError):
        return "内存不足，文件可能太大了。试试分批处理。"
    if isinstance(exc, OSError):
        # 和 core 各 job 用同一份说法，避免界面和日志两套措辞
        from ..core.oserrors import describe

        return describe(exc)
    return "处理时发生了意外问题。详细原因已记录在下方日志里。"


def technical_detail(exc: BaseException) -> str:
    """给日志用的技术细节，不进弹窗。"""
    return f"{type(exc).__name__}: {exc}"


# 界面上的固定文案，集中放这里，方便统一措辞
TEXT = {
    "app_title": "文件批量处理工具",
    "no_files": "还没有添加文件\n\n把文件或文件夹拖到这里，或者点上方按钮添加",
    "preview_first": "请先点击「生成预览」，确认无误后才能执行",
    "preview_empty": "没有可处理的文件，请检查参数设置",
    "output_same_as_source": "输出文件夹不能和源文件所在的文件夹相同，请换一个位置，避免覆盖原文件。",
    "output_not_set": "请先选择输出文件夹。",
    "in_place_warning": "⚠ 将直接修改原文件，改完无法自动撤销，请谨慎使用",
    "in_place_confirm_title": "确认直接修改原文件？",
    "in_place_confirm_body": (
        "你开启了「直接重命名原文件」。\n\n"
        "这会改动原位置的文件，本工具不会保留副本，也无法自动撤销。\n"
        "如果只是想试一下效果，建议关掉这个开关，让结果输出到新文件夹。\n\n"
        "确定要继续吗？"
    ),
    "in_place_confirm_ok": "我确认修改原文件",
    "cancel": "取消",
}
