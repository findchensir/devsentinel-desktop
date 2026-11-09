"""工具函数：纯程序实现，不调用模型。

这是工作流和 Agent 共用的"手"——查日志、搜代码这类确定的活。
后面给 Agent 用时，这些函数会包上 JSON Schema 变成 tools。
"""
from pathlib import Path

# 故障靶场日志目录（11/09 会换成真实靶场）
LOG_DIR = Path(__file__).parent.parent.parent / "fault_lab" / "logs"

MAX_LINES = 50       # 输出截断：日志可能几千行，全塞给模型会爆上下文
CONTEXT_LINES = 2    # 命中行前后带几行上下文


def _search(lines: list[str], kw: list[str], max_lines: int) -> tuple[str, int] | None:
    """在一组日志行里搜关键词。

    返回 (命中片段, 命中的不同关键词数)；无命中返回 None。
    分数 = 不同关键词数（不是命中行数）——防止单个泛词刷屏抢占结果。
    """
    hit: set[int] = set()
    matched: set[str] = set()
    for i, line in enumerate(lines):
        low = line.lower()
        line_kws = [k for k in kw if k in low]
        if line_kws:
            matched.update(line_kws)
            for j in range(max(0, i - CONTEXT_LINES), min(len(lines), i + CONTEXT_LINES + 1)):
                hit.add(j)
    if not hit:
        return None
    ordered = sorted(hit)
    out = [lines[i] for i in ordered[:max_lines]]
    if len(ordered) > max_lines:
        out.append(f"... [已截断，共 {len(ordered)} 行命中，只显示前 {max_lines} 行]")
    return "\n".join(out), len(matched)


def grep_logs(service: str, keywords: list[str], max_lines: int = MAX_LINES) -> str:
    """按服务名 + 关键词过滤日志。

    返回：得分最高的命中片段（截断后，标注来源文件和命中关键词数）。
    设计要点：
    - 遍历所有日志文件评分（命中关键词数），选分数最高的；
      service 文件优先做平局 tie-break。
    - 防止单个泛词（如 "order"）在无关文件里刷屏抢占结果。
    - 返回值是给模型看的，要做截断和格式化，不是原样转发。
    """
    kw = [k.lower() for k in keywords]
    primary = LOG_DIR / f"{service}.log"

    candidates = [primary] if primary.exists() else []
    candidates += [p for p in sorted(LOG_DIR.glob("*.log")) if p != primary]
    if not candidates:
        return f"[无日志文件] {LOG_DIR}"

    best: tuple[str, int, int] | None = None  # (片段, 分数, 是否主文件)
    for i, path in enumerate(candidates):
        lines = path.read_text(encoding="utf-8").splitlines()
        result = _search(lines, kw, max_lines)
        if result is None:
            continue
        snippet, score = result
        is_primary = 1 if i == 0 else 0
        if best is None or (score, is_primary) > (best[1], best[2]):
            best = (f"[来源: {path.name} | 命中关键词 {score}/{len(kw)}]\n{snippet}", score, is_primary)

    if best is None:
        return f"[日志中未命中关键词: {', '.join(keywords)}]"
    return best[0]
