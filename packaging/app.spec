# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（macOS 与 Windows 共用）。

两个目标：
  1. 用户双击就能跑，不需要装 Python，不弹终端窗口；
  2. 体积尽量小——PySide6 装出来有 349MB，其中 QML / Quick / Designer / Lottie
     我们一个都没用到，必须排掉。
"""
import sys
from pathlib import Path

# .spec 执行时没有 __file__，用 SPECPATH 拿到自己的位置
ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ICON_DIR = ROOT / "packaging" / "icon"

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

APP_NAME = "FileBatchTool"          # 内部名保持 ASCII，避免各平台对非 ASCII 的边角问题
DISPLAY_NAME = "文件批量处理工具"     # 用户看到的名字
VERSION = "1.0.0"
BUNDLE_ID = "com.filebatch.tool"

# 只用到 QtCore / QtGui / QtWidgets，其余全部排除
EXCLUDE_QT = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets", "PySide6.QtQuickTest", "PySide6.QtQmlCompiler",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtTest",
    "PySide6.QtSql", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtConcurrent", "PySide6.QtDBus", "PySide6.QtXml",
    "PySide6.QtSvgWidgets", "PySide6.QtPrintSupport", "PySide6.QtNetwork",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtPositioning", "PySide6.QtBluetooth", "PySide6.QtSerialPort",
]

# 开发工具和用不到的标准库
EXCLUDE_DEV = [
    "tkinter", "unittest", "pydoc", "doctest", "pdb", "test",
    "pytest", "_pytest", "PyInstaller", "setuptools", "pip", "wheel",
    "numpy", "pandas", "matplotlib", "scipy", "IPython", "notebook",
    "PyQt5", "PyQt6", "shiboken6_generator",
]

a = Analysis(
    [str(SRC / "filebatch" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Pillow 的格式插件是运行时按需加载的，静态分析看不到
        "PIL.JpegImagePlugin", "PIL.PngImagePlugin", "PIL.WebPImagePlugin",
        "PIL.BmpImagePlugin", "PIL.GifImagePlugin", "PIL.TiffImagePlugin",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDE_QT + EXCLUDE_DEV,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,              # 关键：不弹终端窗口
    disable_windowed_traceback=False,
    argv_emulation=IS_MAC,      # macOS 上支持把文件拖到 Dock 图标
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_DIR / ("app.icns" if IS_MAC else "app.ico")),
    version=str(ROOT / "packaging" / "win_version.txt") if IS_WIN else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(ICON_DIR / "app.icns"),
        bundle_identifier=BUNDLE_ID,
        version=VERSION,
        info_plist={
            "CFBundleName": DISPLAY_NAME,
            "CFBundleDisplayName": DISPLAY_NAME,
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHumanReadableCopyright": "",
            # 不写这个的话 Retina 屏上界面会糊
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "LSApplicationCategoryType": "public.app-category.utilities",
        },
    )
