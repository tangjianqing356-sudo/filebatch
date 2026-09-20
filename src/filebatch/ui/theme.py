"""界面样式。

目标是"简洁现代"，不要程序员调试工具的感觉：浅色底、细边框、圆角、留白充足。
字体按平台给一组回退，Windows 上用微软雅黑，macOS 上用苹方，不写死某一个。
"""
from __future__ import annotations

import sys

# 两个平台的中文字体回退链
if sys.platform == "win32":
    FONT_FAMILY = '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'
    BASE_FONT_SIZE = 13
elif sys.platform == "darwin":
    FONT_FAMILY = '"PingFang SC", "Helvetica Neue", "Hiragino Sans GB", sans-serif'
    BASE_FONT_SIZE = 13
else:
    FONT_FAMILY = '"Noto Sans CJK SC", "WenQuanYi Micro Hei", sans-serif'
    BASE_FONT_SIZE = 13

ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
ACCENT_PRESSED = "#1e40af"
DANGER = "#dc2626"
WARNING = "#ea580c"
SUCCESS = "#16a34a"
MUTED = "#6b7280"
BORDER = "#e5e7eb"
BG = "#f8fafc"
CARD = "#ffffff"

STYLESHEET = f"""
QWidget {{
    font-family: {FONT_FAMILY};
    font-size: {BASE_FONT_SIZE}px;
    color: #111827;
}}
QMainWindow, QDialog {{ background: {BG}; }}

/* 左侧功能列表 */
#SideBar {{
    background: {CARD};
    border-right: 1px solid {BORDER};
}}
#SideBarTitle {{
    font-size: {BASE_FONT_SIZE + 3}px;
    font-weight: 600;
    padding: 18px 16px 10px 16px;
    color: #111827;
}}
#SideBar QListWidget {{
    background: transparent;
    border: none;
    outline: none;
    padding: 4px 8px;
}}
#SideBar QListWidget::item {{
    padding: 10px 12px;
    border-radius: 8px;
    margin: 2px 0;
    color: #374151;
}}
#SideBar QListWidget::item:hover {{ background: #f1f5f9; }}
#SideBar QListWidget::item:selected {{ background: {ACCENT}; color: white; }}
#SideBar QListWidget::item:disabled {{ color: #9ca3af; }}

/* 卡片区块 */
QGroupBox {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px 14px 12px 14px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #374151;
}}

/* 按钮 */
QPushButton {{
    background: {CARD};
    border: 1px solid #d1d5db;
    border-radius: 7px;
    padding: 7px 16px;
    min-height: 20px;
}}
QPushButton:hover {{ background: #f8fafc; border-color: #9ca3af; }}
QPushButton:pressed {{ background: #f1f5f9; }}
QPushButton:disabled {{ color: #9ca3af; background: #f9fafb; border-color: {BORDER}; }}

QPushButton#Primary {{
    background: {ACCENT}; color: white; border: none; font-weight: 600; padding: 9px 22px;
}}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Primary:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#Primary:disabled {{ background: #cbd5e1; color: #f8fafc; }}

QPushButton#Danger {{ background: {DANGER}; color: white; border: none; font-weight: 600; }}
QPushButton#Danger:hover {{ background: #b91c1c; }}

/* 输入控件 */
QLineEdit, QSpinBox, QComboBox {{
    background: {CARD};
    border: 1px solid #d1d5db;
    border-radius: 7px;
    padding: 6px 10px;
    min-height: 20px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ background: #f9fafb; color: #9ca3af; }}
QComboBox::drop-down {{ border: none; width: 22px; }}

/* 表格 */
QTableWidget {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: #f1f5f9;
    selection-background-color: #dbeafe;
    selection-color: #111827;
}}
QHeaderView::section {{
    background: #f8fafc;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 10px;
    font-weight: 600;
    color: #4b5563;
}}
QTableWidget::item {{ padding: 6px 8px; }}

/* 日志 */
QPlainTextEdit {{
    background: #0f172a;
    color: #cbd5e1;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 8px;
    font-family: "SF Mono", Consolas, "Courier New", monospace;
    font-size: {BASE_FONT_SIZE - 1}px;
}}

QProgressBar {{
    background: #e5e7eb; border: none; border-radius: 6px;
    height: 10px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}

#Hint {{ color: {MUTED}; }}
#WarningText {{ color: {WARNING}; font-weight: 600; }}
#DangerText {{ color: {DANGER}; font-weight: 600; }}
#SuccessText {{ color: {SUCCESS}; font-weight: 600; }}
#SectionTitle {{ font-size: {BASE_FONT_SIZE + 2}px; font-weight: 600; padding-bottom: 2px; }}
"""
