"""平台边界验收：那些"只有在真机上才说得准"的场景。

`--selftest` 管依赖完整性，`--acceptance` 管功能走得通，
这里管的是**操作系统的脾气**：中文路径、空格路径、超长路径、
文件被占用、目录不给写、盘符不存在、`.xlsm` 往返。

这些场景在 Mac 上跑也有意义（能验证代码路径），
但真正有价值的结论只能来自 Windows——那边的文件锁、路径上限、
权限模型和 Mac 完全不是一回事。所以每条结果都会标明它在当前平台
算"真的验到了"还是"只是没崩"。

用法：FileBatchTool --platform-check
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

IS_WIN = sys.platform == "win32"

结果: list[tuple[str, bool, str, bool]] = []      # (名称, 通过, 说明, 是否本平台关键)


def _记(名称: str, 通过: bool, 说明: str, 关键: bool = True) -> None:
    结果.append((名称, 通过, 说明, 关键))


def _检查(名称: str, 函数, 关键: bool = True) -> None:
    try:
        _记(名称, True, 函数() or "通过", 关键)
    except AssertionError as e:
        _记(名称, False, f"断言失败：{e}", 关键)
    except Exception as e:
        _记(名称, False, f"{type(e).__name__}: {e}", 关键)


def _不许泄漏(消息: str) -> None:
    """失败原因里不能出现 errno、WinError、异常类名、堆栈这些东西。

    这个工具是给普通用户用的，看到 `[WinError 3]` 既不知道发生了什么，
    也不知道下一步该干嘛。
    """
    for 脏东西 in ("Errno", "errno", "WinError", "Traceback", "OSError", "Exception"):
        assert 脏东西 not in 消息, f"失败原因里漏出了「{脏东西}」：{消息}"


def _写表(path: Path, rows: list[list]) -> Path:
    from openpyxl import Workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def _跑一遍去重(源: Path, 输出: Path) -> int:
    """拿去重当代表：它要读表、写表、建目录，路径相关的坑都会踩到。"""
    from filebatch.core.excel import dedupe_job
    from filebatch.core.excel.dedupe_job import DedupeOptions

    opts = DedupeOptions()
    report = dedupe_job.execute(dedupe_job.plan([源], opts, 输出), opts)
    assert report.failed == 0, report.summary()
    return report.succeeded


# ---------------- 路径 ----------------

def _中文与空格路径() -> str:
    根 = Path(tempfile.mkdtemp(prefix="fb_plat_"))
    源目录 = 根 / "中文 目录 带空格" / "深一层"
    源 = _写表(源目录 / "中文 文件名 带空格.xlsx",
              [["姓名"], ["张三"], ["张三"]])
    输出 = 根 / "输出 目录 中文"
    数 = _跑一遍去重(源, 输出)
    产物 = list(输出.iterdir())
    assert 数 == 1 and 产物, "没产出文件"
    assert 产物[0].stat().st_size > 0
    return f"中文+空格路径读写正常，产出 {产物[0].name}"


def _emoji路径() -> str:
    根 = Path(tempfile.mkdtemp(prefix="fb_plat_"))
    源 = _写表(根 / "表情 😀 目录" / "数据.xlsx", [["A"], ["1"], ["1"]])
    输出 = 根 / "输出 😀"
    _跑一遍去重(源, 输出)
    assert list(输出.iterdir())
    return "emoji 路径读写正常"


def _长路径() -> str:
    """在一条"接近上限但还合法"的深路径下真跑一遍。"""
    from filebatch.core.pathlimits import probe_path_limit, reset_cache

    reset_cache()
    上限 = probe_path_limit()
    根 = Path(tempfile.mkdtemp(prefix="fb_plat_"))

    # 有上限就贴着上限来，没测出上限就取一个足够深的值
    目标长度 = (上限.max_path - 80) if 上限.has_limit else 400
    深 = 根
    while len(str(深 / "层")) < 目标长度:
        深 = 深 / "层"
    源 = _写表(深 / "数据.xlsx", [["A"], ["1"], ["1"]])
    输出 = 深 / "out"
    _跑一遍去重(源, 输出)
    assert list(输出.iterdir())
    return f"{上限.describe()}；在 {len(str(深))} 字符深的目录下读写成功"


def _超限路径被提前拦下() -> str:
    """超过上限的目标必须在**预览阶段**就标成跳过，不能执行到一半甩系统错误。

    没探测到路径上限的平台（Mac / 开了长路径的 Windows）本来就无从超限，
    那种情况只核对"计划阶段不写文件"这一条。
    """
    from filebatch.core.excel import dedupe_job
    from filebatch.core.excel.dedupe_job import DedupeOptions
    from filebatch.core.pathlimits import annotate_over_limit, probe_path_limit, reset_cache

    reset_cache()
    上限 = probe_path_limit()
    根 = Path(tempfile.mkdtemp(prefix="fb_plat_"))
    源 = _写表(根 / "数据.xlsx", [["A"], ["1"], ["1"]])

    超长目录 = 根 / ("很长的目录名" * 30) / ("再来一层" * 30)
    actions = dedupe_job.plan([源], DedupeOptions(), 超长目录)
    assert not 超长目录.exists(), "计划阶段不该建目录"

    拦下 = annotate_over_limit(actions, 上限)
    if not 上限.has_limit:
        return f"本平台未探测到路径长度上限（{上限.describe()}），无从超限；计划阶段未写文件"

    assert 拦下 >= 1, f"探测到上限 {上限.max_path}，但超长目标没被拦下"
    被拦 = [a for a in actions if not a.will_run]
    assert 被拦 and "路径" in (被拦[0].skip_reason or ""), 被拦[0].skip_reason
    return f"超限目标被提前拦下 {拦下} 项，原因：{被拦[0].skip_reason}"


# ---------------- Windows 特有场景 ----------------

def _文件被占用() -> str:
    """源文件被别的程序打开着时，要给人话，不能甩 WinError 32。

    Windows 会真的锁住文件；Mac / Linux 不锁，所以那边这条只算"没崩"。
    """
    根 = Path(tempfile.mkdtemp(prefix="fb_plat_"))
    源 = _写表(根 / "占用中.xlsx", [["A"], ["1"], ["1"]])
    输出 = 根 / "输出"

    # Windows 上 Python 的 open() 默认带 FILE_SHARE_READ，别的进程照样能读，
    # 所以光 open 一下根本模拟不了"文件被 Excel 占着"。
    # Windows CI 上实测这条就走进了"本平台不锁文件"分支，等于什么都没验。
    句柄 = open(源, "rb+")
    上锁 = False
    if IS_WIN:
        try:
            import msvcrt

            msvcrt.locking(句柄.fileno(), msvcrt.LK_NBLCK, 1)
            上锁 = True
        except OSError:
            pass
    try:
        from filebatch.core.excel import dedupe_job
        from filebatch.core.excel.dedupe_job import DedupeOptions

        opts = DedupeOptions()
        report = dedupe_job.execute(dedupe_job.plan([源], opts, 输出), opts)
        if report.failed:
            消息 = report.items[0].message
            _不许泄漏(消息)
            return f"被占用时给出中文提示：{消息}"
        if 上锁:
            return "已真正锁住文件，程序仍能读出来并正常完成（读取不受写锁影响）"
        return "本平台不锁文件，处理正常完成——这条只能证明没崩，真占用要靠真机用 Excel 打开验"
    finally:
        if 上锁:
            try:
                import msvcrt

                msvcrt.locking(句柄.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        句柄.close()


def _输出目录不给写() -> str:
    """没有写权限时要给人话。Windows 的只读位不阻止写入，行为和 POSIX 不同。"""
    根 = Path(tempfile.mkdtemp(prefix="fb_plat_"))
    源 = _写表(根 / "数据.xlsx", [["A"], ["1"], ["1"]])
    只读 = 根 / "只读输出"
    只读.mkdir()
    原权限 = 只读.stat().st_mode
    os.chmod(只读, 0o500)
    try:
        from filebatch.core.excel import dedupe_job
        from filebatch.core.excel.dedupe_job import DedupeOptions

        opts = DedupeOptions()
        report = dedupe_job.execute(dedupe_job.plan([源], opts, 只读), opts)
        if report.failed:
            消息 = report.items[0].message
            _不许泄漏(消息)
            return f"权限不足时给出中文提示：{消息}"
        return "本平台只读位不阻止写入，处理正常完成（Windows 行为相同）"
    finally:
        os.chmod(只读, 原权限)


def _输出目录是源目录() -> str:
    """输出到源目录会让"原文件不覆盖"的承诺失效，必须被拦住。"""
    from filebatch.core.safety import validate_output_dir

    根 = Path(tempfile.mkdtemp(prefix="fb_plat_"))
    源 = _写表(根 / "源" / "数据.xlsx", [["A"], ["1"]])
    错 = validate_output_dir(源.parent, [源])
    assert 错, "输出目录 = 源目录，应该被拦下"
    return f"已拦下：{错}"


def _盘符或根目录不存在() -> str:
    """指向一个不存在的位置时要给人话，不能崩。"""
    根 = Path(tempfile.mkdtemp(prefix="fb_plat_"))
    源 = _写表(根 / "数据.xlsx", [["A"], ["1"], ["1"]])
    不存在 = Path("Z:/没有这个盘/输出") if IS_WIN else Path("/没有这个挂载点/输出")

    from filebatch.core.excel import dedupe_job
    from filebatch.core.excel.dedupe_job import DedupeOptions

    opts = DedupeOptions()
    try:
        report = dedupe_job.execute(dedupe_job.plan([源], opts, 不存在), opts)
    except Exception as e:
        raise AssertionError(f"不该抛异常，应该记成失败项：{type(e).__name__} {e}") from e

    assert report.failed >= 1, "指向不存在的位置居然成功了？"
    消息 = report.items[0].message
    _不许泄漏(消息)
    return f"给出可读失败原因：{消息}"


# ---------------- 文件格式 ----------------

def _xlsm往返() -> str:
    """.xlsm 进 .xlsm 出。真正的宏保留要用带 VBA 的真文件验，见下一条。"""
    from filebatch.core.excel import format_job
    from filebatch.core.excel.format_job import FormatOptions

    根 = Path(tempfile.mkdtemp(prefix="fb_plat_"))
    源 = _写表(根 / "宏表.xlsm", [["姓名", "金额"], ["张三", 100]])
    输出 = 根 / "输出"
    opts = FormatOptions()
    actions = format_job.plan([源], opts, 输出)
    assert actions[0].target.suffix == ".xlsm", f"输出扩展名变成了 {actions[0].target.suffix}"
    report = format_job.execute(actions, opts)
    assert report.failed == 0, report.summary()
    产物 = 输出 / "宏表_格式化.xlsm"
    assert 产物.exists(), "没产出 .xlsm"

    from openpyxl import load_workbook

    ws = load_workbook(产物).active
    assert ws["B2"].value == 100 and isinstance(ws["B2"].value, int)
    return "扩展名保持 .xlsm，数字类型未变"


VBA_流 = "xl/vbaProject.bin"


def _取宏(path: Path) -> bytes | None:
    """把工作簿里的 VBA 工程原样读出来。没有宏就返回 None。

    **不要**用 openpyxl 的 `wb.vba_archive is not None` 来判断有没有宏——
    `keep_vba=True` 只是把源 zip 留着，哪怕一个宏都没有它也不是 None。
    真机验收那条曾经因此对一个完全没有宏的 .xlsm 报"宏保留正常"，
    等于给了假的信心。只有 zip 里真有 xl/vbaProject.bin 才算有宏。
    """
    import zipfile

    try:
        with zipfile.ZipFile(path) as z:
            if VBA_流 not in z.namelist():
                return None
            return z.read(VBA_流)
    except (OSError, zipfile.BadZipFile):
        return None


def _真实宏文件(路径: str) -> str:
    """用户自己提供一个带宏的 .xlsm，验证宏是不是真的还在。

    没法凭空造一个合法的 vbaProject.bin，所以这一条要么靠真文件，要么跳过。
    这里只能证明"VBA 工程的字节被原样带过去了"；
    **宏在 Excel 里还能不能跑，仍然要人工打开确认**。
    """
    from filebatch.core.excel import format_job
    from filebatch.core.excel.format_job import FormatOptions

    源 = Path(路径).expanduser()
    assert 源.exists(), f"找不到文件：{源}"
    assert 源.suffix.lower() == ".xlsm", f"请提供 .xlsm 文件，当前是 {源.suffix}"

    原宏 = _取宏(源)
    assert 原宏 is not None, (
        f"「{源.name}」里没有 VBA 工程（zip 里找不到 {VBA_流}）。"
        "请换一个真正带宏的 .xlsm——在 Excel 里录一个宏另存即可。"
    )

    输出 = Path(tempfile.mkdtemp(prefix="fb_plat_")) / "输出"
    opts = FormatOptions()
    report = format_job.execute(format_job.plan([源], opts, 输出), opts)
    assert report.failed == 0, report.summary()

    产物 = next(输出.glob("*.xlsm"), None)
    assert 产物 is not None, f"没产出 .xlsm，输出目录里是：{[p.name for p in 输出.iterdir()]}"

    新宏 = _取宏(产物)
    assert 新宏 is not None, f"宏没保住：输出文件里找不到 {VBA_流}"
    assert 新宏 == 原宏, (
        f"VBA 工程的内容变了（原 {len(原宏)} 字节，现 {len(新宏)} 字节）"
    )
    return (
        f"VBA 工程 {len(原宏)} 字节原样保留（{产物.name}）；"
        "宏能不能跑请再用 Excel 打开确认一次"
    )


def _格式统一默认不改样式() -> str:
    """封板后的核心承诺，在真机上再核一遍。"""
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font

    from filebatch.core.excel import format_job
    from filebatch.core.excel.format_job import FormatOptions

    根 = Path(tempfile.mkdtemp(prefix="fb_plat_"))
    源 = 根 / "混排.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "一月"
    for r in [["表头"], ["左"], ["中"], ["右"]]:
        ws.append(r)
    ws["A1"].font = Font(name="Times New Roman", size=13)
    ws["A2"].font = Font(name="宋体", size=14)
    ws["A3"].font = Font(name="Arial", size=9)
    ws["A1"].alignment = Alignment(horizontal="right")
    ws["A2"].alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws["A3"].alignment = Alignment(horizontal="center")
    二月 = wb.create_sheet("二月")
    二月.append(["数字"])
    二月.append([1234])
    wb.save(源)

    输出 = 根 / "输出"
    opts = FormatOptions()
    report = format_job.execute(format_job.plan([源], opts, 输出), opts)
    assert report.failed == 0, report.summary()

    得 = load_workbook(输出 / "混排_格式化.xlsx")
    assert 得.sheetnames == ["一月", "二月"], f"工作表丢了：{得.sheetnames}"
    w = 得["一月"]
    字体 = [(w[f"A{i}"].font.name, w[f"A{i}"].font.size) for i in (1, 2, 3)]
    assert 字体 == [("Times New Roman", 13), ("宋体", 14), ("Arial", 9)], 字体
    对齐 = [w[f"A{i}"].alignment.horizontal for i in (1, 2, 3)]
    assert 对齐 == ["right", "left", "center"], 对齐
    assert w["A2"].alignment.vertical == "top" and w["A2"].alignment.wrap_text is True
    assert isinstance(得["二月"]["A2"].value, int), "数字被改成了文本"
    assert w["A1"].font.bold is True, "表头加粗没生效"
    return "字体/字号/对齐默认保留，多工作表与数字类型未变"


# ---------------- 入口 ----------------

def run(xlsm: str | None = None) -> int:
    import platform

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    print("=" * 60)
    print(f"平台边界验收（{platform.platform()}）")
    print("=" * 60)
    if not IS_WIN:
        print("注意：当前不是 Windows。文件占用、权限、盘符这几条在这里只能")
        print("      证明代码路径不崩，真正的结论要在 Windows 真机上看。")
        print("-" * 60)

    _检查("中文与空格路径", _中文与空格路径)
    _检查("emoji 路径", _emoji路径)
    _检查("长路径读写", _长路径)
    _检查("超限路径预览阶段拦截", _超限路径被提前拦下, 关键=IS_WIN)
    _检查("源文件被占用", _文件被占用, 关键=IS_WIN)
    _检查("输出目录没有写权限", _输出目录不给写, 关键=IS_WIN)
    _检查("输出目录 = 源目录", _输出目录是源目录)
    _检查("输出位置不存在", _盘符或根目录不存在)
    _检查(".xlsm 往返", _xlsm往返)
    _检查("格式统一默认不改样式", _格式统一默认不改样式)

    if xlsm:
        _检查("真实宏文件的宏保留", lambda: _真实宏文件(xlsm))
    else:
        _记("真实宏文件的宏保留", True,
            "已跳过：需要 --xlsm <带宏的.xlsm> 才能验，造不出合法的 vbaProject.bin",
            False)

    失败 = 0
    for 名称, ok, 说明, 关键 in 结果:
        标 = "[通过]" if ok else "[失败]"
        尾 = "" if 关键 else "（本平台仅供参考）"
        print(f"{标} {名称}{尾}")
        print(f"       {说明}")
        if not ok:
            失败 += 1
    print("-" * 60)
    print(f"共 {len(结果)} 项，失败 {失败} 项")
    return 1 if 失败 else 0


if __name__ == "__main__":
    参数 = sys.argv
    文件 = 参数[参数.index("--xlsm") + 1] if "--xlsm" in 参数 else None
    try:
        sys.exit(run(文件))
    except Exception:
        traceback.print_exc()
        sys.exit(2)
