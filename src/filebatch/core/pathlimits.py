"""路径长度上限的实测与提示。

为什么要实测而不是写死 260：
  - Windows 10 1607 起可以在注册表打开 LongPathsAware，开了之后能到 32767；
  - 不同盘、网络盘、映射盘的表现也不一样；
  - macOS / Linux 限制的是**单个文件名**（通常 255 字节），整条路径可以很长。
写死一个数字，要么在支持长路径的机器上白白拦住用户，要么在不支持的机器上放过去然后报系统错误。

所以这里的做法是：在目标目录里实际试着建一个长名文件，试出来多长算多长。
探测文件用唯一名字，建完立刻删掉，不碰用户的任何文件。
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

# 超过这个长度还能建，就认为这台机器没有实际意义上的路径限制
NO_LIMIT_PROBE = 400

# Windows 传统上限，仅用于提示文案，不作为判定依据
WINDOWS_CLASSIC_MAX = 260


@dataclass
class PathLimit:
    """实测结果。max_path <= 0 表示没测出限制。"""

    max_path: int = 0
    max_name: int = 0
    probe_error: str | None = None

    @property
    def has_limit(self) -> bool:
        return self.max_path > 0

    def describe(self) -> str:
        if self.probe_error:
            return f"无法探测路径长度上限：{self.probe_error}"
        if not self.has_limit:
            # 措辞刻意保守：探测只能说明"试到 400 字符还能建"，
            # 不能保证所有 API、所有路径形态都没有限制。
            return f"当前环境检测到可支持较长路径（已试到 {NO_LIMIT_PROBE} 字符仍可创建）"
        return f"当前输出位置的路径长度上限约为 {self.max_path} 个字符"


def _可以创建(probe_root: Path, 总长: int) -> bool:
    """试着造出一条总长度达到 总长 的路径，看系统让不让。

    关键：必须用**多层短目录**堆长度，不能用一个超长文件名。
    否则在 macOS / Linux 上会先撞上 255 字节的单文件名上限，
    被误判成"总路径上限 316"，而这两个限制完全是两回事。
    """
    base_len = len(str(probe_root))
    if base_len >= 总长 - 12:
        return True                      # 探测根目录本身就够长，测不了

    # 用 a/a/a/... 这样的短目录往下堆，最后放一个短名文件
    每层 = 2                              # "a" + 分隔符
    文件名 = "f.tmp"
    需要层数 = max(0, (总长 - base_len - len(文件名) - 1) // 每层)

    深目录 = probe_root
    try:
        for _ in range(需要层数):
            深目录 = 深目录 / "a"
        深目录.mkdir(parents=True, exist_ok=True)
        target = 深目录 / 文件名
        with open(target, "wb") as f:
            f.write(b"0")
        return True
    except OSError:
        return False
    finally:
        _清理(probe_root)


_缓存: PathLimit | None = None


def probe_path_limit(directory: Path | None = None) -> PathLimit:
    """实测路径长度上限。

    **在系统临时目录里测，不碰用户的任何目录。**
    这一步发生在预览阶段，而预览必须是只读的——早期版本在输出目录里建探测文件，
    等于偷偷把还没确认的输出目录创建了出来，违反了"计划阶段不写文件"的约定。

    在临时目录测同样有效：Windows 的 MAX_PATH 是注册表里的全局开关（LongPathsEnabled），
    不是按卷设置的，所以在哪测结果都一样。
    `directory` 参数保留只是为了兼容调用方，不再使用。
    """
    global _缓存
    if _缓存 is not None:
        return _缓存

    import tempfile

    try:
        probe_root = Path(tempfile.mkdtemp(prefix="fb_probe_"))
    except OSError as e:
        return PathLimit(probe_error=str(e))

    try:
        if _可以创建(probe_root, NO_LIMIT_PROBE):
            # 能建超长路径，说明没有 MAX_PATH 这类限制（Linux/macOS，或已开长路径的 Windows）
            _缓存 = PathLimit(max_path=0, max_name=_探测文件名上限(probe_root))
            return _缓存

        # 有限制，二分找出实际能用的最大值
        低, 高 = len(str(probe_root)) + 12, NO_LIMIT_PROBE
        while 低 < 高:
            中 = (低 + 高 + 1) // 2
            if _可以创建(probe_root, 中):
                低 = 中
            else:
                高 = 中 - 1
        _缓存 = PathLimit(max_path=低, max_name=_探测文件名上限(probe_root))
        return _缓存
    except Exception as e:  # 探测本身绝不能让整个预览挂掉
        return PathLimit(probe_error=f"{type(e).__name__}: {e}")
    finally:
        _清理(probe_root, 删自己=True)


def reset_cache() -> None:
    """清掉探测缓存，测试用。"""
    global _缓存
    _缓存 = None


def _清理(root: Path, 删自己: bool = False) -> None:
    """删掉探测留下的临时目录树。失败也不抛，探测不该影响主流程。"""
    import shutil

    try:
        if 删自己:
            shutil.rmtree(root, ignore_errors=True)
            return
        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    except OSError:
        pass


def _探测文件名上限(directory: Path) -> int:
    """单个文件名的长度上限（macOS/Linux 通常 255）。"""
    低, 高 = 8, 300
    while 低 < 高:
        中 = (低 + 高 + 1) // 2
        名字 = "p" + uuid.uuid4().hex[:7] + "x" * (中 - 8)
        target = directory / 名字
        try:
            with open(target, "wb") as f:
                f.write(b"0")
            低 = 中
        except OSError:
            高 = 中 - 1
        finally:
            try:
                if target.exists():
                    target.unlink()
            except OSError:
                pass
    return 低


def too_long_reason(target: Path, limit: PathLimit) -> str | None:
    """这个目标路径会不会超限。返回中文说明，None 表示没问题。"""
    if limit.probe_error:
        return None                      # 测不出来就不拦，交给执行时的错误提示

    if limit.has_limit and len(str(target)) > limit.max_path:
        提示 = (
            f"文件路径过长（{len(str(target))} 个字符，当前位置上限约 {limit.max_path}）。"
            "Windows 无法创建该文件，请缩短文件名，或把输出目录移动到更靠近磁盘根目录的位置。"
        )
        if sys.platform == "win32" and limit.max_path <= WINDOWS_CLASSIC_MAX + 5:
            提示 += "（也可以在系统设置里开启 Windows 长路径支持）"
        return 提示

    if limit.max_name and len(target.name) > limit.max_name:
        return (
            f"文件名过长（{len(target.name)} 个字符，系统上限 {limit.max_name}）。"
            "请缩短前缀、后缀或统一改名的内容。"
        )
    return None


def annotate_over_limit(actions: list, limit: PathLimit) -> int:
    """把会超长的计划项改成"跳过"，并写明中文原因。返回被拦下的数量。

    放在预览阶段做，用户在点执行之前就能看到问题，而不是执行到一半报系统错误。
    """
    拦下 = 0
    for act in actions:
        if not act.will_run or act.target is None:
            continue
        reason = too_long_reason(act.target, limit)
        if reason:
            act.skip_reason = reason
            拦下 += 1
    return 拦下
