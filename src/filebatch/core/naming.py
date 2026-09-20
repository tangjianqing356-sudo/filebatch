"""重命名规则引擎。

刻意做成不碰文件系统的纯函数，这样规则本身可以被完整单元测试覆盖，
界面里的"预览"用的也是同一份逻辑，所见即所得。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class CaseMode(str, Enum):
    KEEP = "keep"
    LOWER = "lower"
    UPPER = "upper"


class NumberPosition(str, Enum):
    NONE = "none"
    PREFIX = "prefix"
    SUFFIX = "suffix"


@dataclass
class NameRule:
    """一条重命名规则。各项都可以单独用，也可以叠加。

    执行顺序：基础名 -> 查找替换 -> 大小写 -> 前后缀 -> 编号
    """

    # 完全替换主名（留空表示保留原名）
    base_name: str = ""
    find: str = ""
    replace: str = ""
    use_regex: bool = False
    prefix: str = ""
    suffix: str = ""
    case_mode: CaseMode = CaseMode.KEEP
    number_position: NumberPosition = NumberPosition.NONE
    number_start: int = 1
    number_digits: int = 3
    number_separator: str = "_"
    new_extension: str = ""   # 留空表示保持原扩展名

    def __post_init__(self) -> None:
        """把字符串归一成枚举。

        CaseMode / NumberPosition 都是 str 的子类，经过 Qt 的 QVariant 往返
        （QComboBox.currentData()）之后会退化成普通 str。那样 `is NumberPosition.NONE`
        这种身份比较就恒为假——用户明明选了"不编号"，却照样被加上编号。
        在这里统一归一，调用方传字符串还是枚举都不会出错。
        """
        if not isinstance(self.case_mode, CaseMode):
            try:
                object.__setattr__(self, "case_mode", CaseMode(self.case_mode))
            except ValueError:
                object.__setattr__(self, "case_mode", CaseMode.KEEP)
        if not isinstance(self.number_position, NumberPosition):
            try:
                object.__setattr__(self, "number_position", NumberPosition(self.number_position))
            except ValueError:
                object.__setattr__(self, "number_position", NumberPosition.NONE)

    def validate(self) -> str | None:
        """返回 None 表示规则可用，否则返回中文错误说明。"""
        if self.use_regex and self.find:
            try:
                re.compile(self.find)
            except re.error as e:
                return f"正则表达式有误：{e}"
        if self.number_digits < 1 or self.number_digits > 10:
            return "编号位数需要在 1~10 之间"
        if self.number_start < 0:
            return "起始编号不能是负数"
        illegal = set('/\\:*?"<>|')
        for field_name, value in (("前缀", self.prefix), ("后缀", self.suffix), ("主名", self.base_name)):
            bad = illegal & set(value)
            if bad:
                return f"{field_name}含有文件名不允许的字符：{''.join(sorted(bad))}"
        return None

    def apply(self, original_stem: str, index: int) -> str:
        """算出新的主名（不含扩展名）。index 从 0 开始。"""
        stem = self.base_name if self.base_name else original_stem

        if self.find:
            if self.use_regex:
                stem = re.sub(self.find, self.replace, stem)
            else:
                stem = stem.replace(self.find, self.replace)

        if self.case_mode is CaseMode.LOWER:
            stem = stem.lower()
        elif self.case_mode is CaseMode.UPPER:
            stem = stem.upper()

        stem = f"{self.prefix}{stem}{self.suffix}"

        if self.number_position is not NumberPosition.NONE:
            number = str(self.number_start + index).zfill(self.number_digits)
            sep = self.number_separator
            if self.number_position is NumberPosition.PREFIX:
                stem = f"{number}{sep}{stem}" if stem else number
            else:
                stem = f"{stem}{sep}{number}" if stem else number

        return stem

    def resolve_extension(self, original_suffix: str) -> str:
        if not self.new_extension:
            return original_suffix
        ext = self.new_extension.strip()
        return ext if ext.startswith(".") else f".{ext}"


def sanitize_filename(name: str, replacement: str = "_") -> str:
    """把文件名里不合法的字符换掉，避免生成一个存不下去的名字。"""
    cleaned = re.sub(r'[/\\:*?"<>|\x00-\x1f]', replacement, name)
    cleaned = cleaned.strip().rstrip(".")
    return cleaned or "未命名"
