"""验证工具注册表：模型能不能看懂 schema 并正确发起 tool_call。

用法: .venv/bin/python try_tools.py
"""
import asyncio
import json

from services.llm.client import client, provider
from services.agent.registry import tool_schemas, call_tool


async def main():
    question = "订单服务 15:00 起响应变慢，帮我查一下 15:00 之后日志里 timeout 相关的行"

    resp = await client.chat.completions.create(
        model=provider.model,
        messages=[{"role": "user", "content": question}],
        tools=tool_schemas(),
        temperature=0.3,
    )
    msg = resp.choices[0].message

    if not msg.tool_calls:
        print("模型没有调工具，直接回了:", msg.content)
        return

    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)
        print(f"模型决定调: {tc.function.name}")
        print(f"参数: {json.dumps(args, ensure_ascii=False)}")
        result = call_tool(tc.function.name, args)
        print(f"执行结果:\n{result[:400]}\n---")


asyncio.run(main())
