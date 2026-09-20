"""常用预设。

只放最高频的三种，一选就把参数填好。不做模板管理、不做保存/导入那一套。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.naming import CaseMode, NumberPosition


@dataclass(frozen=True)
class RenamePreset:
    name: str
    hint: str
    values: dict = field(default_factory=dict)


CUSTOM = RenamePreset("自定义", "自己填下面的规则")

RENAME_PRESETS: list[RenamePreset] = [
    CUSTOM,
    RenamePreset(
        "统一加前缀",
        "保留原文件名，在前面统一加上你填的前缀",
        {
            "base_name": "",
            "prefix": "2026_",
            "suffix": "",
            "number_position": NumberPosition.NONE,
            "case_mode": CaseMode.KEEP,
        },
    ),
    RenamePreset(
        "照片自动编号",
        "把文件名统一改成「照片_001、照片_002…」",
        {
            "base_name": "照片",
            "prefix": "",
            "suffix": "",
            "number_position": NumberPosition.SUFFIX,
            "number_start": 1,
            "number_digits": 3,
            "number_separator": "_",
            "case_mode": CaseMode.KEEP,
        },
    ),
    RenamePreset(
        "统一改成小写",
        "把文件名里的英文字母全部改成小写",
        {
            "base_name": "",
            "prefix": "",
            "suffix": "",
            "number_position": NumberPosition.NONE,
            "case_mode": CaseMode.LOWER,
        },
    ),
]
