import json
from typing import AsyncIterator

from services.llm.client import client, provider
from .registry import tool_schemas, call_tool

SYSTEM_PROMPT = (
    "你是 DevSentinel 故障排查 Agent。你可以调用工具排查问题："
    "read_log 查日志证据，search_code 定位代码。"
    "证据足够时给出根因分析和修复建议；证据不足时继续调用工具。"
    "结论要引用具体证据（日志行、文件:行号），不要凭空猜测。"
)


async def agent_loop(question: str, max_steps: int = 10) -> AsyncIterator[dict]:
    """手写 Agent 循环：模型决定调工具 → 执行 → 回填 → 再问，直到给结论。

    通过 yield 推送事件：
      step        每轮开始的进度标记
      tool_call   模型决定调用的工具 + 参数
      tool_result 工具执行结果
      content     最终答案（模型不再调工具）
      error       异常
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question}]
    fail_count: dict[str, int] = {}   # 工具失败次数统计
    seen: set[str] = set() # 检测重复调用
    total_tokens = 0
    TOKEN_BUDGET = 30000      # 单次请求预算

    for step in range(max_steps):          # 步数上限：防止死循环/烧钱
        yield {"type": "step", "name": f"round_{step + 1}",
               "label": f"第 {step + 1} 轮思考"}
        try:
            resp = await client.chat.completions.create(
                model=provider.model,
                messages=messages,
                tools=tool_schemas(),
                temperature=0.3,
            )
            total_tokens += resp.usage.total_tokens if resp.usage else 0  # 每轮累计真实消耗
            if total_tokens > TOKEN_BUDGET:
                messages.append({"role": "system",
                                 "content": "Token 使用已超过预算，请基于已有信息直接给结论，不要再调工具"})
                # 不带 tools 的最后一次调用：强制模型收尾而不是继续调工具
                resp = await client.chat.completions.create(
                    model=provider.model, messages=messages, temperature=0.3)
                yield {"type": "content",
                       "text": f"[已达 token 预算 {TOKEN_BUDGET}]\n\n" + (resp.choices[0].message.content or "")}
                return
            
        except Exception as e:
            yield {"type": "error", "code": "llm_call_failed",
                   "message": str(e), "retryable": step + 1 < max_steps}
            return

        msg = resp.choices[0].message

        # 模型不调工具了 → content 就是最终答案
        if not msg.tool_calls:
            yield {"type": "content", "text": msg.content or ""}
            return

        # 如果有 tool_calls 且有 content，则先输出思考
        # 去除首尾空白，避免空行被误认为思考内容
        thought = (msg.content or "").strip()
        if msg.tool_calls and thought:
            yield {"type": "thought", "text": thought}

        # 有 tool_calls → 先记"模型要调工具"，再逐个执行回填
        messages.append(msg)
        for tc in msg.tool_calls:
            sig = f"{tc.function.name}:{tc.function.arguments}"
            yield {"type": "tool_call", "name": tc.function.name,
                   "args": tc.function.arguments, "id": tc.id}

            # 检测重复调用
            if sig in seen:
                result = "[提示] 该工具已用相同参数调用过，请换策略或直接给结论"
            else:
                seen.add(sig)
                try:
                    args = json.loads(tc.function.arguments)
                    result = call_tool(tc.function.name, args)
                except json.JSONDecodeError:
                    result = f"[错误] 工具参数不是合法 JSON: {tc.function.arguments}"

            # 连续失败计数：错误也是 Observation，但失败多次要提示模型换思路
            if result.startswith("[错误]"):
                fail_count[tc.function.name] = fail_count.get(tc.function.name, 0) + 1
                if fail_count[tc.function.name] >= 2:
                    result += " 已多次失败，建议换其他工具或直接说明无法获取"
            else:
                fail_count[tc.function.name] = 0

            yield {"type": "tool_result", "name": tc.function.name,
                   "result": result[:2000], "id": tc.id}   # 截断保护，防单次结果爆上下文

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
        # 回到循环顶部：模型看到工具结果，再决定下一步

    yield {"type": "error", "code": "max_steps",
           "message": f"达到最大步数 {max_steps}，请人工介入", "retryable": False}
