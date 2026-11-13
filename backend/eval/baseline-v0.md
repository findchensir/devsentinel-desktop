# 基线 v0（2026-11-13）

## 运行条件

| 项 | 值 |
|---|---|
| Agent | 手写循环 `services/agent/loop.py`（commit `154fb0a`） |
| 模型 | DeepSeek（`services/llm/client.py` 默认配置） |
| 工具 | read_log / search_code / git_log / git_show |
| 靶场代码 | `order-service` @ `main`（`1dd632f`），5 个故障同时存在 |
| 输入 | 各场景 yaml 的 `symptom` 原文，单轮 |
| 运行方式 | `.venv/bin/python eval/run_baseline.py`，每场景 1 次 |
| 原始记录 | `eval/runs/20261113-1541/`（SSE 事件 jsonl + 答案 md + summary.json） |
| 判定 | 人工对照 `scenarios/*.yaml` 的 `root_cause` |

## 结果

| 场景 | 难度 | 判定 | 步数 | 工具调用 | 耗时 | 备注 |
|---|---|---|---|---|---|---|
| 01 pool-exhausted | easy | ✅ 命中 | 7 | 12 | 14.9s | 根因、commit、代码行都对；但为日志 `max=5 (was 50)` 与代码 `10→1` 的矛盾编了"配置热更新"解释 |
| 02 zero-price-orders | medium | ✅ 命中 | 5 | 7 | 9.8s | 证据最干净：日志行 + 代码行 + diff + 计算验证 |
| 03 request-hang | medium | ❌ 未命中 | 7 | 15 | 14.6s | 归因到连接池；`while True` 重试从未被查到 |
| 04 silent-logs | hard | 🟡 命中但主次颠倒 | 6 | 11 | 11.9s | 定位到日志级别 commit，但称连接池才是"真正的故障" |
| 05 false-out-of-stock | easy | ✅ 命中 | 5 | 7 | 9.3s | 条件反转、diff、修复建议都对 |

**根因命中率：4/5（80%）**；严格口径（主因判断正确）：3/5（60%）。
平均 6 步、10.4 次工具调用、12.1s。工具 `[错误]` 0 次，事件 id 全部配对，5 场均正常 `done`。

## 失败分析

### 03 未命中：证据被锚定在错误的日志上

调用轨迹：`read_log(service="order-service")` → 读到的是 `order-service.log`（连接池故障叙事），
**场景自己的 `03-request-hang.log` 从未被读取**。之后 14 次调用都在围绕连接池找佐证。
`git_log` 的结果里其实出现了 `98e6bb8 add retry for db insert`，但模型没有 `git_show` 它，
也没有搜 `insert_order` / `retry`。

- 工具层：`read_log` 指定 service 时只读 `{service}.log`，不会落到场景日志
- 目标层：先入为主——拿到第一条看似合理的证据后只找佐证，不找反证

### 04 主次颠倒：同一个污染源

同样先读了 `order-service.log` 的连接池日志，所以把连接池当成主故障，日志级别降为"掩盖因素"。

### 01 的编造解释

`order-service.log` 里写的是 `max=5 (was 50)`，代码是 `10 → 1`，两者对不上。
模型没有把矛盾当成疑点报告，而是自行编了"配置热更新"来圆——这是"不报错但答错"的典型样本。

## 靶场自身问题（影响基线可信度）

1. **所有场景共享 `order-service.log`**，且内容是场景 01 的叙事 → 对 03/04 是系统性干扰。
   要么按场景隔离日志目录，要么把它当作"噪声日志"写进场景设计里。
2. **`order-service.log` 和代码数值不一致**（`5/50` vs `1/10`），应修正。
3. **5 个 bug 同时存在**：这次是有意为之（更接近真实），但要在评测口径里写明。
4. 每场景只跑 1 次，模型有随机性，80% 不是稳定值——W7 评测要每场景多跑取均值。

## 下一步可验证的假设

| 改动 | 预期影响 | 对应计划 |
|---|---|---|
| 按场景隔离日志 | 03/04 命中率上升 | 靶场修正 |
| prompt 要求"列出至少两个候选根因并逐一排除" | 减少锚定 | 11/16 |
| 工具描述引导"看到可疑 commit 就 git_show" | 03 能查到 98e6bb8 | 11/16 |
| 证据矛盾时必须显式报告 | 消除 01 类编造 | 12/09 Reporter 校验 |
