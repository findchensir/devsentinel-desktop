"""工具函数：纯程序实现，不调用模型。

这是工作流和 Agent 共用的"手"——查日志、搜代码这类确定的活。
后面给 Agent 用时，这些函数会包上 JSON Schema 变成 tools。
"""
from pathlib import Path

# 故障靶场日志目录（11/09 会换成真实靶场）
LOG_DIR = Path(__file__).parent.parent.parent / "fault_lab" / "logs"

MAX_LINES = 50       # 输出截断：日志可能几千行，全塞给模型会爆上下文
CONTEXT_LINES = 2    # 命中行前后带几行上下文

def grep_logs(service: str, keywords: list[str], max_lines: int = MAX_LINES) -> str:
    """按服务名 + 关键词过滤日志。

    返回：命中的日志片段（截断后）。没有命中返回空串。
    设计要点：返回值是给模型看的，要做截断和格式化，不是原样转发。
    """
    log_file = LOG_DIR / f"{service}.log"
    if not log_file.exists():
        return f"[无日志文件] {log_file}"

    lines = log_file.read_text(encoding="utf-8").splitlines()
    kw = [k.lower() for k in keywords]

    # 命中的行号集合（含上下文行）
    hit: set[int] = set()
    for i, line in enumerate(lines):
        low = line.lower()
        if any(k in low for k in kw):
            for j in range(max(0, i - CONTEXT_LINES), min(len(lines), i + CONTEXT_LINES + 1)):
                hit.add(j)

    if not hit:
        return f"[日志中未命中关键词: {', '.join(keywords)}]"

    ordered = sorted(hit)
    truncated = len(ordered) > max_lines
    out = [lines[i] for i in ordered[:max_lines]]
    if truncated:
        out.append(f"... [已截断，共 {len(ordered)} 行命中，只显示前 {max_lines} 行]")
    return "\n".join(out)
