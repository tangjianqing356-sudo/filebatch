# 文件批量处理工具

给普通用户用的桌面小工具：批量重命名、分类整理、图片处理、Excel 工具箱、PDF 拆合、文本替换。
全中文界面，拖拽操作，**所有操作都先预览再执行，默认不覆盖、不动原文件**。

## 当前进度

| 功能 | 核心逻辑 | 界面 |
|---|---|---|
| 批量重命名 / 编号 | ✅ | ✅ |
| 文件分类整理 | ✅ | ✅ |
| 图片批处理 | ✅ | ✅ |
| Excel 工具箱（6 项，见下） | ✅ | ✅ |
| PDF 拆分 / 合并 | ✅ | ✅ |
| 文本查找替换 | ✅ | ✅ |

### Excel 工具箱

| 子功能 | 做什么 |
|---|---|
| 合并 | 多个表按列名对齐合并成一个，缺列补空 |
| 去重 | 按选定的列找重复记录，每组留第一条或最后一条 |
| 两表对比 | 按关键列比两张表，输出「仅A表有 / 仅B表有 / 内容不同 / 汇总」四张工作表 |
| 数据清洗 | 删空行、去首尾空格、合并多余空格、去掉单元格内换行 |
| 批量拆表 | 按某一列的值把一张表拆成多张 |
| 格式统一 | 表头加粗、对齐、边框、列宽、数字格式；字体默认不改，你选了才改 |

**能力边界（不会静默处理，遇到会明确提示）：**

- 支持 `.xlsx` / `.xlsm` / `.csv` / `.tsv`。旧版 `.xls` 需要先用 Excel 另存为 `.xlsx`；
  加密文件、`.xlsb` 会在预览里单独列出原因，不会被跳过也不会被悄悄改坏。
- 数据清洗**不做数据类型转换**：身份证号、以 0 开头的编号、`3-5` 这类文本一律原样保留，
  不会变成科学计数法或日期。
- 格式统一**只改你明确要求改的东西**。字体、字号、正文对齐、表头对齐
  默认都是「保留原设置（不修改）」——只有你主动挑了具体的值，才会去改对应的属性；
  也不会按 Windows / macOS 偷偷换字体。
  注意「保留」指的是不修改该单元格对应的那个属性，不是文件字节级不变：
  用 openpyxl 打开再保存，xlsx 内部的 XML 和压缩结构会重新生成。
- 格式统一在原文件的副本上改样式，**不重建工作簿**，所以多个工作表、
  数字和日期的类型都不受影响（不会把数字变成文本）。
- 图表、图片、条件格式、表格对象、宏在当前验收样例中已验证可保留，
  但复杂 Excel 仍可能存在兼容性差异。**数据透视表、切片器、ActiveX / 窗体控件、
  外部链接、复杂宏工作簿**风险更高，预览里会单独标出来。重要文件请先备份。
- 拆表按取值不多的列（部门、地区、月份）用；超过数量上限会拦下来并提示多半是选错了列。

V1 功能已全部接入界面，双平台打包已完成。

## 开发环境

```bash
# 一次性准备（uv 会自己装好 Python 3.12，不需要管理员权限）
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.12
uv pip install -r requirements-dev.txt --python .venv/bin/python
```

```bash
# 启动界面
PYTHONPATH=src ./.venv/bin/python -m filebatch
```

```bash
# 跑测试
./.venv/bin/python -m pytest
```

```bash
# 生成界面截图（无头，不需要显示器）
QT_QPA_PLATFORM=offscreen PYTHONPATH=src ./.venv/bin/python scripts/screenshot.py
```

```bash
# 测冷启动和内存
QT_QPA_PLATFORM=offscreen ./.venv/bin/python scripts/benchmark.py
```

```bash
# 检查不同缩放比例（Windows 125%/150%、Mac Retina）下的布局
./.venv/bin/python scripts/check_dpi.py
```

## 架构

一条贯穿全局的规矩：**plan → 预览 → execute → 日志**。

```
core/  纯业务逻辑，不依赖 Qt，可以单独测
  ├─ plan_xxx()  只读，算出"会发生什么"，绝不写文件
  └─ execute()   按计划执行，每个文件独立 try，一个失败不影响其余
                 接受 on_progress / should_cancel 回调，供界面显示进度和中断

ui/    只管界面和交互，不重新实现任何业务逻辑
  ├─ pages/base_page.py  六个功能页的公共骨架，安全规则统一在这里实现
  ├─ worker.py           把 core 的 execute 搬到 QThread
  └─ scan_worker.py      文件扫描也在后台线程，拖入几万个文件不卡界面

新增一个功能页只要回答四个问题：参数控件长什么样、参数合不合法、
计划怎么算、计划怎么执行。安全规则子类想绕都绕不过去。
```

安全约定（有测试锁死）：

- 默认复制到新目录，原文件不动
- 目标重名自动加 `_1 _2`，**绝不覆盖**已有文件
- 同一批里算出相同新名字的，互相之间也不覆盖
- 输出目录不能等于源目录
- 危险开关默认关闭，开启有警告，执行前二次确认，回车不会误触
- 中断只停止后续任务，已完成的文件不回滚

## 目录结构

```
src/filebatch/
├── core/              业务逻辑（1491 行）
│   ├── result.py      计划/结果模型 + 中文日志
│   ├── safety.py      防覆盖、防误操作
│   ├── scan.py        文件收集
│   ├── naming.py      重命名规则引擎（纯函数）
│   ├── rename_job.py  批量重命名
│   ├── classify_job.py 分类整理
│   ├── image_job.py   图片处理
│   ├── table_job.py   表格合并
│   ├── pdf_job.py     PDF 拆合
│   └── text_job.py    文本替换
├── ui/                界面（1224 行）
│   ├── app.py         入口
│   ├── main_window.py 主窗口
│   ├── theme.py       样式
│   ├── messages.py    异常 -> 人话
│   ├── worker.py      后台线程
│   ├── widgets/       通用控件
│   └── pages/         各功能页面
tests/                 126 个测试（1368 行）
scripts/               截图和性能测量
docs/screenshots/      界面截图
```


## 打包与发布

### macOS（Intel）

```bash
./scripts/build_macos.sh
```

产物 `dist_app/文件批量处理工具_macOS_Intel.zip`（88MB 应用，zip 后 36MB）。

**两个坑，脚本里已经绕开，改动时别踩回去**：

1. PyInstaller 会给 .app 做 ad-hoc 签名。**打包完成后往 bundle 里塞任何文件都会破坏封印**，
   Gatekeeper 的提示会从"无法验证开发者"升级成"应用已损坏"，用户直接被吓退。
   使用说明要放在 .app **外面**。
2. 改 bundle 名字之后要 `codesign --force --deep --sign -` 重新签一次。

**Gatekeeper 实测**：未公证，首次双击会提示"Apple 无法检查其是否包含恶意软件"，
右键 → 打开 → 再点一次"打开"即可，之后不再提示。要去掉这一步需要 Apple Developer ID + 公证，
V1 先不做。

### Windows（x64）

必须在真 Windows 上构建，不在 Mac 上硬做。用 `.github/workflows/build.yml`
在 `windows-latest` 上跑：测试 → DPI 检查 → 打包 → 自检 → 验收 → 各 DPI 截图 → 上传 zip。

推仓库后 CI 自动跑：

```bash
gh repo create filebatch --private --source=. --push
```

### 为什么用 onedir 而不是 onefile

实测（macOS Intel，各 3 次）：

| | 体积 | 冷启动 |
|---|---|---|
| onedir | 88MB（zip 36MB） | 948–1477 ms |
| onefile | 35MB 单文件 | **4796–5568 ms** |

onefile 每次启动都要把 88MB 解压到临时目录，慢 4~5 倍；Windows 上还容易被杀毒误报。
普通用户稳定使用比"单个 exe 好看"重要，所以用 onedir。

### 自验开关

打包后的程序带三个开关，用来验证**冻结后**的产物而不是开发环境：

```bash
文件批量处理工具.app/Contents/MacOS/FileBatchTool --selftest          # 依赖完整性
文件批量处理工具.app/Contents/MacOS/FileBatchTool --acceptance        # 6 功能完整跑一遍
文件批量处理工具.app/Contents/MacOS/FileBatchTool --measure-startup   # 冷启动与内存
```
