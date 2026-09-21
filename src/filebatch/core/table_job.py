"""兼容层：Excel / CSV 合并已经迁到 core/excel/merge_job.py。

Excel 功能从 1 个涨到 6 个之后，再往这一个文件里堆就没法看了，
所以按功能拆进了 core/excel/。这里保留原有的导入路径，
既有代码（ui/pages/table_page.py）和既有测试都不用改。

新代码请直接用 filebatch.core.excel.*，不要再往这个文件里加东西。
"""
from .excel.merge_job import (  # noqa: F401
    CANDIDATE_ENCODINGS,
    CSV_SUFFIXES,
    EXCEL_SUFFIXES,
    MAX_ROWS,
    SUPPORTED_SUFFIXES,
    MergeOptions,
    align_rows,
    execute,
    plan_merge,
    read_table,
)

__all__ = [
    "CANDIDATE_ENCODINGS",
    "CSV_SUFFIXES",
    "EXCEL_SUFFIXES",
    "MAX_ROWS",
    "SUPPORTED_SUFFIXES",
    "MergeOptions",
    "align_rows",
    "execute",
    "plan_merge",
    "read_table",
]
