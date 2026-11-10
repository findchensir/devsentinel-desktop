"""工具函数：纯程序实现，不调用模型。

这是工作流和 Agent 共用的"手"——查日志、搜代码这类确定的活。
后面给 Agent 用时，这些函数会包上 JSON Schema 变成 tools。
"""
from pathlib import Path

# 故障靶场目录
LAB_DIR = Path(__file__).parent.parent.parent / "fault_lab"
LOG_DIR = LAB_DIR / "logs"
CODE_DIR = LAB_DIR / "order-service" / "src"   # 靶场服务源码

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

def _in_window(line: str, start: str, end: str) -> bool:
    """时间窗过滤：行前缀时间戳与 start/end 做字符串前缀比较。

    兼容 "15:00" 和 "2026-11-08 15:00" 两种粒度：
    短前缀按"尾部对齐"比（取行时间戳的最后 len(start) 个字符），
    长前缀按"头部对齐"比。不起作用的行（无时间戳前缀）默认放行。
    """
    ts = line[:19]  # "YYYY-MM-DD HH:MM:SS" 刚好 19 字符
    if not ts or not ts[0].isdigit():
        return True
    tod = ts[11:]  # "HH:MM:SS" 部分
    if start:
        # 短前缀（如 "15:00"）比时分秒；长前缀（含日期）比完整时间戳
        field = tod if len(start) <= 8 else ts
        if field[:len(start)] < start:
            return False
    if end:
        field = tod if len(end) <= 8 else ts
        if field[:len(end)] > end:
            return False
    return True


def read_log(service: str = "",
             keywords: list[str] = [],
             start: str = "",
             end: str = "",
             max_lines: int = MAX_LINES) -> str:
    """按 服务 → 时间窗 → 关键词 三层过滤读取日志。

    返回：命中片段（标注来源/时间窗/命中数），给模型做证据。
    所有参数可缺省：service 空 = 全目录搜索，keywords 空 = 时间窗内全部行。
    """
    # ① 服务过滤：选候选文件
    primary = LOG_DIR / f"{service}.log" if service else None
    if primary and primary.exists():
        files = [primary]
    elif service:
        return f"[无日志文件] {LOG_DIR / (service + '.log')}，可省略 service 搜全部"
    else:
        files = sorted(LOG_DIR.glob("*.log"))
    if not files:
        return f"[无日志文件] {LOG_DIR}"

    kw = [k.lower() for k in keywords]
    best: tuple[str, int, int] | None = None  # (片段, 分数, 是否主文件)

    for i, path in enumerate(files):
        lines = path.read_text(encoding="utf-8").splitlines()
        total = len(lines)

        # ② 时间过滤
        if start or end:
            lines = [l for l in lines if _in_window(l, start, end)]
            if not lines:
                continue

        # ③ 关键词过滤（空关键词 = 全量返回时间窗内行）
        if kw:
            result = _search(lines, kw, max_lines)
            if result is None:
                continue
            snippet, score = result
        else:
            snippet, score = "\n".join(lines[:max_lines]), 0
            if len(lines) > max_lines:
                snippet += f"\n... [已截断，共 {len(lines)} 行]"

        is_primary = 1 if i == 0 else 0
        if best is None or (score, is_primary) > (best[1], best[2]):
            meta = f"[来源: {path.name}"
            if start or end:
                meta += f" | 时间窗: {start or '-∞'}~{end or '+∞'}"
            meta += f" | 命中关键词 {score}/{len(kw)}" if kw else f" | 共 {total} 行"
            meta += "]"
            best = (f"{meta}\n{snippet}", score, is_primary)

    if best is None:
        if kw:
            return f"[未命中] 关键词 {keywords} 在指定范围内无结果，可换关键词或扩大时间窗"
        return f"[无日志] 时间窗 {start}~{end} 内无日志行"
    return best[0]

CODE_CONTEXT_LINES = 3  # 代码命中行前后各带 3 行（比日志多，代码要上下文才能看懂）


def search_code(query: str, max_lines: int = 30) -> str:
    """在靶场服务源码里做子串搜索，返回 文件:行号 + 上下文片段。

    返回格式：
        src/db.py:14: POOL_MAX = 1
        （命中行带行号，前后各 CODE_CONTEXT_LINES 行上下文，文件间分隔）
    给 Agent 用：模型拿到"文件:行号"才能指认证据位置。
    """
    if not CODE_DIR.exists():
        return f"[无代码目录] {CODE_DIR}"

    q = query.lower()
    hits: list[str] = []
    hit_count = 0

    for path in sorted(CODE_DIR.glob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        rel = path.relative_to(CODE_DIR.parent)  # src/db.py

        # 收集命中行号（含上下文）
        hit_idx: set[int] = set()
        for i, line in enumerate(lines):
            if q in line.lower():
                hit_count += 1
                for j in range(max(0, i - CODE_CONTEXT_LINES), min(len(lines), i + CODE_CONTEXT_LINES + 1)):
                    hit_idx.add(j)

        if not hit_idx:
            continue

        # 输出 文件:行号: 内容，上下文块间用 -- 分隔
        ordered = sorted(hit_idx)
        block = [f"--- {rel} ---"]
        prev = -2
        for idx in ordered:
            if idx != prev + 1:
                block.append("  ...")
            block.append(f"{idx + 1:>4}: {lines[idx]}")
            prev = idx
        hits.append("\n".join(block))

    if not hits:
        return f"[代码中未命中: {query}] 可尝试更短的关键词或搜函数名/变量名"

    body = "\n\n".join(hits)
    out_lines = body.splitlines()
    if len(out_lines) > max_lines:
        body = "\n".join(out_lines[:max_lines]) + f"\n... [已截断，共 {len(out_lines)} 行]"
    return f"[代码搜索: {query} | {hit_count} 处命中]\n{body}"
