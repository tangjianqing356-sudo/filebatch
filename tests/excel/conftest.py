"""Excel 工具箱测试的公共辅助。"""
import csv
from pathlib import Path

import pytest
from openpyxl import Workbook


@pytest.fixture
def 写xlsx():
    def _写(path: Path, rows: list[list], sheet: str = "Sheet1") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        ws.title = sheet
        for r in rows:
            ws.append(r)
        wb.save(path)
        return path
    return _写


@pytest.fixture
def 写csv():
    def _写(path: Path, rows: list[list], encoding: str = "utf-8") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding=encoding, newline="") as f:
            csv.writer(f).writerows(rows)
        return path
    return _写


@pytest.fixture
def 销售表(写xlsx, tmp_path):
    """一张带重复、带空行、带脏空格的样例表。"""
    return 写xlsx(tmp_path / "销售.xlsx", [
        ["姓名", "地区", "金额"],
        ["张三", "华东", "100"],
        ["李四", "华南", "200"],
        ["张三", "华东", "100"],      # 和第 1 行完全重复
        ["王五 ", "华东", "300"],      # 姓名带尾随空格
        ["", "", ""],                 # 空行
        ["张三", "华北", "150"],      # 姓名重复但地区不同
    ])
