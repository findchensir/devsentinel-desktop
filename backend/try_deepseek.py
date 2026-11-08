"""
最小化验证脚本：不经过 FastAPI，直接在终端调用一次 DeepSeek，用来确认：
  1. API Key 配置正确
  2. 网络能访问 DeepSeek
  3. services/llm/ 的封装能正常工作

运行方式（在 backend 目录下）：
    .venv/bin/python try_deepseek.py
"""

import asyncio

from services import llm

# system_prompt 
system_prompt = """
你是一个专业运维工程师，擅长解决各种技术问题,你只回答50个字以内
"""


async def ask_stream(messages: list[dict], temperature: float, system_prompt: str,  max_tokens=10) -> None:
    """跑一次流式调用，打印正文和 token 用量"""
    async for event in llm.chat_stream(messages, temperature=temperature, system_prompt=system_prompt, max_tokens=max_tokens):
        if event["type"] == "content":
            print(event["text"], end="", flush=True)
        elif event["type"] == "usage":
            print(
                f"  [usage] 输入={event['prompt_tokens']} "
                f"输出={event['completion_tokens']} "
                f"合计={event['total_tokens']}"
            )


async def main() -> None:
    # 用诊断场景的问题，更贴近值班助手
    messages = [{"role": "user", "content": "MySQL 连接超时可能是什么原因？"}]

    # 实验：同一个问题，3 档温度各跑 3 次，对比输出稳定性
    for temp in [0.0, 0.3, 1.5]:
        print(f"\n========== temperature={temp} ==========")
        for i in range(1):  # 只跑一次，避免输出过多
            print(f"\n--- 第{i+1}次 ---")
            await ask_stream(messages, temperature=temp, system_prompt=system_prompt, max_tokens=10)
            print()


if __name__ == "__main__":
    # llm 里的函数都是 async 的，普通脚本需要用 asyncio.run 来启动事件循环执行它们。
    asyncio.run(main())
