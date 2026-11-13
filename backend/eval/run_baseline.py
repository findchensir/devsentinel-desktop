"""手动基线：逐个场景调用 Agent，保存原始 SSE 事件流 + 过程统计，并生成 report.md。

命中判定是启发式初判：答案里出现该场景的 fault_commit hash 视为命中
（每个场景的 bug 都由一次特定提交引入，答对根因基本会引用它），
"主次颠倒/编造解释"这类细粒度问题仍需人工复核 answer.md。

用法：
  跑一轮:   .venv/bin/python eval/run_baseline.py
  只补报告: .venv/bin/python eval/run_baseline.py --report runs/20261113-1541
"""
import json
import sys
import time
from pathlib import Path

import httpx

BASE = Path(__file__).parent
SCENARIO_DIR = BASE.parent / "fault_lab" / "scenarios"
OUT_DIR = BASE / "runs" / time.strftime("%Y%m%d-%H%M")
URL = "http://127.0.0.1:8000/api/agent/diagnose_agent"


def read_field(path: Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""


def run(path: Path) -> dict:
    symptom = read_field(path, "symptom")
    events, t0 = [], time.time()
    # trust_env=False：不读系统代理，否则本地请求会被代理转发返回 502
    with httpx.Client(trust_env=False, timeout=httpx.Timeout(10, read=180)) as client, \
            client.stream("POST", URL, json={"messages": [{"role": "user", "content": symptom}]}) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    elapsed = time.time() - t0

    (OUT_DIR / f"{path.stem}.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")

    calls = [e for e in events if e["type"] == "tool_call"]
    results = {e.get("id"): e for e in events if e["type"] == "tool_result"}
    answer = "".join(e.get("text", "") for e in events if e["type"] == "content")
    (OUT_DIR / f"{path.stem}.answer.md").write_text(answer, encoding="utf-8")
    return {
        "scenario": path.stem,
        "symptom": symptom,
        "steps": sum(e["type"] == "step" for e in events),
        "tool_calls": len(calls),
        "tools": [c["name"] for c in calls],
        "tool_errors": sum(results.get(c.get("id"), {}).get("result", "").startswith("[错误]") for c in calls),
        "unpaired": sum(c.get("id") not in results for c in calls),
        "errors": [e for e in events if e["type"] == "error"],
        "done": any(e["type"] == "done" for e in events),
        "seconds": round(elapsed, 1),
        "answer_chars": len(answer),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        print(f"▶ {path.stem} ...", flush=True)
        s = run(path)
        summary.append(s)
        print(f"  steps={s['steps']} tools={s['tool_calls']} {s['tools']} "
              f"errors={len(s['errors'])} {s['seconds']}s", flush=True)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    build_report(OUT_DIR)
    print(f"\n输出目录: {OUT_DIR}")


def build_report(run_dir: Path) -> None:
    """扫一遍运行目录，生成 report.md：每个场景一行，自动初判 + 诊断信号。"""
    lines = [
        f"# 运行报告 {run_dir.name}\n",
        "判定 = 答案中是否出现该场景的 fault_commit（启发式初判，需人工复核）\n",
        "| 场景 | 判定 | 应命中 commit | 场景日志被读 | 步数 | 工具调用 | 耗时 |",
        "|---|---|---|---|---|---|---|",
    ]
    hits = 0
    for yaml_path in sorted(SCENARIO_DIR.glob("*.yaml")):
        stem = yaml_path.stem
        answer_path = run_dir / f"{stem}.answer.md"
        jsonl_path = run_dir / f"{stem}.jsonl"
        if not answer_path.exists() or not jsonl_path.exists():
            lines.append(f"| {stem} | ⚪ 无数据 | | | | | |")
            continue

        answer = answer_path.read_text(encoding="utf-8")
        results_text = "\n".join(
            e["result"] for e in
            (json.loads(l) for l in jsonl_path.read_text(encoding="utf-8").splitlines())
            if e.get("type") == "tool_result"
        )
        summary = next(
            (s for s in json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
             if s["scenario"] == stem), {})

        commit = read_field(yaml_path, "fault_commit").split()[0].strip("()")
        log_file = Path(read_field(yaml_path, "log_file")).name

        hit = commit in answer
        hits += hit
        log_read = log_file in results_text
        lines.append(
            f"| {stem} | {'✅' if hit else '❌'} | `{commit}` | "
            f"{'✅' if log_read else '⚠️ 未读'} | {summary.get('steps','')} | "
            f"{summary.get('tool_calls','')} | {summary.get('seconds','')}s |"
        )
    lines += ["", f"自动初判命中率: {hits}/5", ""]
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "--report":
        build_report(BASE / sys.argv[2])
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        print(f"▶ {path.stem} ...", flush=True)
        s = run(path)
        summary.append(s)
        print(f"  steps={s['steps']} tools={s['tool_calls']} {s['tools']} "
              f"errors={len(s['errors'])} {s['seconds']}s", flush=True)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    build_report(OUT_DIR)
    print(f"\n输出目录: {OUT_DIR}")


if __name__ == "__main__":
    main()
