#!/usr/bin/env bash
# macOS 打包。
#
# 有两条容易踩的坑，这个脚本就是为了绕开它们：
#   1. 打包完成后**不能**再往 .app 里塞任何文件——PyInstaller 会给 bundle 做
#      ad-hoc 签名，事后加文件会破坏封印，Gatekeeper 会从"无法验证开发者"
#      升级成"应用已损坏"，用户直接被吓退；
#   2. 改完 bundle 名字要重新 ad-hoc 签一次，否则同样封印失效。
set -e
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
APP_NAME="文件批量处理工具"
OUT="dist_app"

echo "──── 1/5 生成图标 ────"
PYTHONPATH=src $PY scripts/make_icon.py

echo "──── 2/5 PyInstaller 打包 ────"
rm -rf "$OUT" build
$PY -m PyInstaller packaging/app.spec --distpath "$OUT" --workpath build --noconfirm --clean 2>&1 | tail -1
rm -rf "$OUT/FileBatchTool"          # onedir 的中间产物，.app 里已经有一份

echo "──── 3/5 改成中文名并重新 ad-hoc 签名 ────"
mv "$OUT/FileBatchTool.app" "$OUT/$APP_NAME.app"
codesign --force --deep --sign - "$OUT/$APP_NAME.app" 2>&1 | grep -v "replacing existing signature" || true
codesign --verify --deep --strict "$OUT/$APP_NAME.app" && echo "  签名校验通过（ad-hoc）"

echo "──── 4/5 验证打包产物 ────"
EXE="$OUT/$APP_NAME.app/Contents/MacOS/FileBatchTool"
"$EXE" --selftest 2>&1 | grep -vE "qt.qpa" | tail -2
"$EXE" --acceptance 2>&1 | grep -vE "qt.qpa|IMKCF" | tail -2

echo "──── 5/5 打发布包 ────"
# 使用说明放在 .app **外面**，不能塞进 bundle 里破坏签名
mkdir -p "$OUT/发布"
cp -R "$OUT/$APP_NAME.app" "$OUT/发布/"
cp README.md "$OUT/发布/使用说明.md"
cd "$OUT/发布"
ditto -c -k --keepParent . "../${APP_NAME}_macOS_Intel.zip"
cd ../..
rm -rf "$OUT/发布"

echo ""
echo "  .app  $(du -sh "$OUT/$APP_NAME.app" | awk '{print $1}')"
echo "  zip   $(du -sh "$OUT/${APP_NAME}_macOS_Intel.zip" | awk '{print $1}')"
