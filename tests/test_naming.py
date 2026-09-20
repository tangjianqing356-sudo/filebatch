from filebatch.core.naming import CaseMode, NameRule, NumberPosition, sanitize_filename


def test_默认规则不改变文件名():
    rule = NameRule()
    assert rule.apply("报告", 0) == "报告"


def test_加前缀后缀():
    rule = NameRule(prefix="2026_", suffix="_终稿")
    assert rule.apply("年度报告", 0) == "2026_年度报告_终稿"


def test_普通查找替换():
    rule = NameRule(find="草稿", replace="终稿")
    assert rule.apply("项目草稿v2", 0) == "项目终稿v2"


def test_正则查找替换():
    rule = NameRule(find=r"\s+", replace="_", use_regex=True)
    assert rule.apply("我的 年度  报告", 0) == "我的_年度_报告"


def test_正则错误能被校验出来():
    rule = NameRule(find="[未闭合", use_regex=True)
    assert "正则表达式有误" in (rule.validate() or "")


def test_自动编号加在前面并补零():
    rule = NameRule(number_position=NumberPosition.PREFIX, number_start=1, number_digits=3)
    assert rule.apply("照片", 0) == "001_照片"
    assert rule.apply("照片", 9) == "010_照片"


def test_自动编号加在后面():
    rule = NameRule(number_position=NumberPosition.SUFFIX, number_start=5, number_digits=2)
    assert rule.apply("发票", 0) == "发票_05"


def test_完全替换主名加编号是最常见的用法():
    rule = NameRule(
        base_name="产品图",
        number_position=NumberPosition.SUFFIX,
        number_start=1,
        number_digits=2,
        number_separator="-",
    )
    assert rule.apply("IMG_9281", 0) == "产品图-01"
    assert rule.apply("DSC_0001", 1) == "产品图-02"


def test_大小写转换():
    assert NameRule(case_mode=CaseMode.LOWER).apply("ReadMe", 0) == "readme"
    assert NameRule(case_mode=CaseMode.UPPER).apply("ReadMe", 0) == "README"


def test_规则叠加时顺序是替换再大小写再前后缀最后编号():
    rule = NameRule(
        find="draft",
        replace="final",
        case_mode=CaseMode.UPPER,
        prefix="[",
        suffix="]",
        number_position=NumberPosition.SUFFIX,
        number_digits=2,
    )
    assert rule.apply("draft-01", 0) == "[FINAL-01]_01"


def test_扩展名默认保持不变():
    assert NameRule().resolve_extension(".JPG") == ".JPG"
    assert NameRule(new_extension="png").resolve_extension(".jpg") == ".png"
    assert NameRule(new_extension=".png").resolve_extension(".jpg") == ".png"


def test_非法字符会被校验拦下():
    assert "不允许的字符" in (NameRule(prefix="a/b").validate() or "")


def test_清理非法文件名():
    assert sanitize_filename("a/b:c*d") == "a_b_c_d"
    assert sanitize_filename("   ") == "未命名"
    assert sanitize_filename("结尾的点...") == "结尾的点"


def test_编号位数越界会被校验拦下():
    assert "编号位数" in (NameRule(number_digits=0).validate() or "")


# ---- 回归测试：Qt 的 QVariant 会把 str 子类枚举退化成普通字符串 ----

def test_传字符串当枚举用也不会出错():
    """QComboBox.currentData() 返回的是退化后的普通 str，
    早期版本用 `is` 比较导致"选了不编号却照样编号"。"""
    rule = NameRule(number_position="none", case_mode="keep")
    assert rule.number_position is NumberPosition.NONE
    assert rule.case_mode is CaseMode.KEEP
    assert rule.apply("报告", 0) == "报告", "选了不编号就不该加编号"


def test_字符串形式的其它枚举值同样能归一():
    assert NameRule(number_position="prefix").apply("a", 0) == "001_a"
    assert NameRule(case_mode="upper").apply("abc", 0) == "ABC"


def test_无法识别的枚举值退回安全默认():
    rule = NameRule(number_position="乱写的值", case_mode="也是乱写")
    assert rule.number_position is NumberPosition.NONE
    assert rule.case_mode is CaseMode.KEEP
