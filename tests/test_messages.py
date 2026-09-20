"""错误提示必须是人话，而且跨平台都对。"""
import errno

from filebatch.ui.messages import humanize, technical_detail


def test_常见错误都有中文提示():
    assert "其他程序" in humanize(PermissionError(errno.EACCES, "Permission denied"))
    assert "已经被移动" in humanize(FileNotFoundError(errno.ENOENT, "No such file"))
    assert "磁盘空间不足" in humanize(OSError(errno.ENOSPC, "No space left"))


def test_文件名过长的提示跨平台都能触发():
    """回归测试：ENAMETOOLONG 在 Linux 是 36、macOS 是 63，
    早期版本写死 36，导致这条提示在 Mac 上永远不出现。"""
    msg = humanize(OSError(errno.ENAMETOOLONG, "File name too long"))
    assert "太长" in msg
    assert "缩短" in msg


def test_只读位置有专门提示():
    assert "只读" in humanize(OSError(errno.EROFS, "Read-only file system"))


def test_未知异常也不会把堆栈甩给用户():
    msg = humanize(ValueError("some internal detail"))
    assert "some internal detail" not in msg, "技术细节不该进弹窗正文"
    assert "日志" in msg


def test_技术细节单独留给日志():
    detail = technical_detail(ValueError("boom"))
    assert "ValueError" in detail and "boom" in detail
