"""值班助手 v0：固定工作流（提取 → grep 日志 → 总结）

和工作流的区别：步骤是代码写死的，模型只在第 1、3 步出现，
不决定流程走向。这是后面"真 Agent"（模型自己选工具）的 baseline。
"""
from typing import AsyncIterator

from services import llm
from services.llm.models import FaultInfo
from .tools import grep_logs

# 第 1 步提取用的 system prompt：只提取要素，不做诊断
EXTRACT_PROMPT = (
    "你是故障信息提取助手。从用户描述的报错/现象中提取结构化故障要素，"
    "以 JSON 输出。service 推断最可能的服务名（如 order-service、payment-service），"
    "severity 只能是 low/medium/high/critical。"
    "keywords 用于在日志文件里做字符串检索：必须输出日志中可能出现的"
    "英文术语/字段名/错误片段（如 timeout、total=、ERROR、pool exhausted、"
    "0.00），不要输出中文描述词或完整长句；每个词尽量短，可给 4~8 个。"
)

# 第 3 步总结用的 system prompt
SUMMARIZE_PROMPT = (
    "你是 DevSentinel 值班助手。根据用户描述、提取的故障要素和日志片段，"
    "给出根因分析和修复建议。要引用日志中的具体证据，不要泛泛而谈。"
)


async def diagnose_workflow(user_input: str) -> AsyncIterator[dict]:
    """固定三步流水线，每步通过事件告诉前端进度。"""

    # ---------- 步骤 1：LLM 提取故障要素（结构化） ----------
    yield {"type": "step", "name": "extract", "label": "提取故障要素"}
    try:
        result = await llm.chat_structured(
            [{"role": "user", "content": user_input}],
            schema=FaultInfo,
            system_prompt=EXTRACT_PROMPT,
        )
        fault = result["data"]
        yield {"type": "step_result", "name": "extract", "data": fault}
    except Exception as e:
        yield {"type": "error", "code": "extract_failed", "message": f"要素提取失败：{e}", "retryable": False}
        yield {"type": "done"}
        return

    # ---------- 步骤 2：程序 grep 日志（不调模型） ----------
    yield {"type": "step", "name": "grep", "label": "检索日志"}
    logs = grep_logs(fault["service"], fault["keywords"])
    # 日志片段也作为事件发给前端（可折叠展示"Agent 看到了什么"）
    yield {"type": "step_result", "name": "grep", "data": logs}

    # ---------- 步骤 3：LLM 总结诊断（流式） ----------
    yield {"type": "step", "name": "summarize", "label": "综合诊断"}
    summarize_msgs = [{
        "role": "user",
        "content": (
            f"用户描述：{user_input}\n\n"
            f"提取的故障要素：{fault}\n\n"
            f"日志片段：\n{logs}\n\n"
            f"请给出根因分析和修复建议。"
        ),
    }]
    async for event in llm.chat_stream(summarize_msgs, system_prompt=SUMMARIZE_PROMPT):
        yield event   # 透传 content / usage / error 事件（done 由接口层统一发）


# 导出给 server.py
__all__ = ["diagnose_workflow"]
