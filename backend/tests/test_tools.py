"""tools.py 契约测试。

工具的约定（call_tool 依赖它）：永不抛异常，错误/未命中用约定前缀的
字符串返回——"[错误]"、"[未命中]"、"[无日志]"。模型靠这些提示自我纠错，
前缀断了整个纠错链路就断了。
"""
import pytest

from services.agent import tools


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    d = tmp_path / "logs"
    d.mkdir()
    (d / "order-service.log").write_text(
        "2026-11-05 14:59:58 INFO  heartbeat ok\n"
        "2026-11-05 15:00:03 ERROR acquire connection timeout after 500ms\n"
        "2026-11-05 15:00:04 ERROR acquire connection timeout after 500ms\n"
        "no timestamp line mentioning timeout\n",
        encoding="utf-8",
    )
    (d / "other.log").write_text(
        "2026-11-05 15:00:05 INFO unrelated noise\n", encoding="utf-8"
    )
    monkeypatch.setattr(tools, "LOG_DIR", d)
    return d


@pytest.fixture
def code_dir(tmp_path, monkeypatch):
    d = tmp_path / "src"
    d.mkdir()
    (d / "db.py").write_text(
        "import sqlite3\n\nPOOL_MAX = 1\n\ndef acquire():\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tools, "CODE_DIR", d)
    return d


class TestInWindow:
    def test_short_prefix_uses_time_of_day(self):
        line = "2026-11-05 15:00:03 ERROR x"
        assert tools._in_window(line, "15:00", "")
        assert not tools._in_window(line, "15:01", "")

    def test_long_prefix_uses_full_timestamp(self):
        line = "2026-11-05 15:00:03 ERROR x"
        assert tools._in_window(line, "2026-11-05 14:00", "2026-11-05 16:00")
        assert not tools._in_window(line, "2026-11-06 00:00", "")

    def test_line_without_timestamp_passes(self):
        assert tools._in_window("no timestamp at all", "15:00", "16:00")


class TestSearch:
    def test_scores_distinct_keywords_not_lines(self):
        # "timeout" 命中 3 行，"error" 命中 1 行——分数是 2 不是 4
        lines = ["timeout", "timeout", "error timeout", "timeout"]
        result = tools._search(lines, ["timeout", "error", "miss"], 50)
        assert result is not None
        _, score = result
        assert score == 2

    def test_no_hit_returns_none(self):
        assert tools._search(["a", "b"], ["zzz"], 50) is None

    def test_truncation_marker(self):
        lines = ["hit"] * 100
        snippet, _ = tools._search(lines, ["hit"], 10)
        assert "[已截断" in snippet
        assert snippet.count("hit") == 10


class TestReadLog:
    def test_keyword_hit_marks_source(self, log_dir):
        out = tools.read_log(service="order-service", keywords=["timeout"])
        assert "[来源: order-service.log" in out
        assert "timeout" in out

    def test_unknown_service_returns_hint(self, log_dir):
        out = tools.read_log(service="no-such-svc", keywords=["x"])
        assert out.startswith("[无日志文件]")
        assert "可省略 service" in out

    def test_keyword_miss_returns_hint(self, log_dir):
        out = tools.read_log(keywords=["zzz-no-hit"])
        assert out.startswith("[未命中]")

    def test_time_window_filters_lines(self, log_dir):
        out = tools.read_log(start="15:00", end="15:00")
        assert "15:00:03" in out
        assert "14:59:58" not in out

    def test_empty_keywords_returns_window_lines(self, log_dir):
        out = tools.read_log(service="order-service")
        assert "共 4 行" in out
        # 无时间戳行默认放行
        assert "no timestamp" in out

    def test_contract_never_raises(self, log_dir):
        out = tools.read_log(service="missing", keywords=["x"], start="99:99")
        assert isinstance(out, str)


class TestSearchCode:
    def test_hit_format_file_line(self, code_dir):
        out = tools.search_code("POOL_MAX")
        assert "--- src/db.py ---" in out
        assert "POOL_MAX = 1" in out
        assert "处命中" in out

    def test_miss_returns_hint(self, code_dir):
        out = tools.search_code("zzz-no-hit")
        assert out.startswith("[代码中未命中")


class TestGitTools:
    """对真实靶场仓库的冒烟测试（integration）。"""

    def test_git_log_lists_commits(self):
        out = tools.git_log(10)
        assert "optimize pool config" in out

    def test_git_show_rejects_injection(self):
        for bad in ["", "abc; rm -rf /", "12345g", "abc", "x" * 41]:
            out = tools.git_show(bad)
            assert out.startswith("[错误]"), f"未拦截: {bad!r}"

    def test_git_show_valid_commit(self):
        out = tools.git_show("783f100")
        assert out.startswith("[git show 783f100]")
        assert "POOL_MAX" in out
