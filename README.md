# 文件批量处理工具

给普通用户用的桌面小工具：批量重命名、分类整理、图片处理、表格合并、PDF 拆合、文本替换。
全中文界面，拖拽操作，**所有操作都先预览再执行，默认不覆盖、不动原文件**。

## 当前进度

| 功能 | 核心逻辑 | 界面 |
|---|---|---|
| 批量重命名 / 编号 | ✅ | ✅ |
| 文件分类整理 | ✅ | ✅ |
| 图片批处理 | ✅ | ✅ |
| Excel / CSV 合并 | ✅ | ✅ |
| PDF 拆分 / 合并 | ✅ | ✅ |
| 文本查找替换 | ✅ | ✅ |

V1 功能已全部接入界面，下一步是双平台打包。

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
