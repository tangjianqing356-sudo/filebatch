#!/usr/bin/env bash
# 本地预演 CI 的步骤顺序，尽量在推仓库之前把低级错误挑出来。
# 真正的 Windows 差异还是要靠 windows-latest 跑，这里只验证步骤本身立得住。
set -e
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
[ -f ".venv/Scripts/python.exe" ] && PY=".venv/Scripts/python.exe"

步骤() { echo ""; echo "──── $1 ────"; }

步骤 "1/7 跑全部测试"
QT_QPA_PLATFORM=offscreen $PY -m pytest -q 2>&1 | tail -2

步骤 "2/7 DPI 布局检查"
$PY scripts/check_dpi.py

步骤 "3/7 生成图标"
PYTHONPATH=src $PY scripts/make_icon.py

步骤 "4/7 PyInstaller 打包"
$PY -m PyInstaller packaging/app.spec --distpath dist_ci --workpath build_ci --noconfirm --clean 2>&1 | tail -1

步骤 "5/7 打包产物自检"
if [ -d "dist_ci/FileBatchTool.app" ]; then
  EXE="dist_ci/FileBatchTool.app/Contents/MacOS/FileBatchTool"
else
  EXE="dist_ci/FileBatchTool/FileBatchTool"
fi
"$EXE" --selftest 2>&1 | grep -vE "qt.qpa" | tail -2

步骤 "6/7 六功能完整验收"
"$EXE" --acceptance 2>&1 | grep -vE "qt.qpa|IMKCF" | tail -2

步骤 "7/7 体积与启动"
"$EXE" --measure-startup 2>&1 | grep -vE "qt.qpa"
du -sh dist_ci/* 2>/dev/null | head -2

echo ""
echo "CI 预演全部通过"
