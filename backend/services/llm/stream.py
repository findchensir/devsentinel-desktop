"""
流式对话：模型每生成一小段文字就立刻返回，不用等全部生成完（打字机效果）。

注意边界：本文件只产出「业务事件」字典（content / usage），
SSE 格式（data: ...、[DONE]）是传输层的事，在 server.py 里组装。
"""

from typing import AsyncIterator

from .errors import translate

from services import config
from .client import DEFAULT_SYSTEM_PROMPT, build_messages, client, usage_to_dict, provider


# 当前模式不能带上历史对话记录，每次都是独立的对话
# async def chat_stream(
#     user_message: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT
# ) -> AsyncIterator[dict]:

# """改造：支持历史对话记录"""
async def chat_stream(
    history: list[dict], 
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    stop: str | list[str] | None = None,
) -> AsyncIterator[dict]:
    """
    为什么需要流式？
    模型生成是逐 token 串行的，一段几百字的回复可能要几秒到几十秒。
    非流式要等全部生成完才能看到内容，体验很差；
    流式可以像 ChatGPT 那样边生成边显示，首字延迟从「几秒」降到「几百毫秒」。

    这是一个「异步生成器」(async generator)：用 `async for` 遍历它。
    吐出的每一项是带 "type" 字段的事件字典：

        {"type": "content", "text": "一小段模型回复文本"}   # 若干个
        {"type": "usage", "prompt_tokens": ..., ...}        # 最后 1 个

    用法：
        async for event in chat_stream("你好"):
            if event["type"] == "content":
                print(event["text"], end="", flush=True)
    """
    # messages = build_messages(user_message, system_prompt)
    messages = build_messages(history, system_prompt)
    try:
        # stream=True 之后，create() 不再返回一个完整的 response，
        # 而是返回一个可以异步遍历的「事件流」，每个事件叫一个 chunk（数据块）。
        stream = await client.chat.completions.create(
            model=provider.model,
            messages=messages,
            stream=True,
            # include_usage=True 让 DeepSeek 在最后一个 chunk 里返回 token 用量统计。
            stream_options={"include_usage": True},
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
        )

        async for chunk in stream:
            # ① 先检查 usage：它是「结尾 chunk」，choices 为空但 usage 有值。
            #    必须先查它再查 choices，否则会被下面的判空逻辑跳过去。
            if chunk.usage is not None:
                usage = usage_to_dict(chunk.usage)
                if usage:
                    # type 标记让调用方能区分这是用量信息而不是文本
                    yield {"type": "usage", **usage}
                continue

            # ② 如果 chunk.choices 为空，说明这个 chunk 没有文本内容，直接跳过。
            if not chunk.choices:
                continue
            # delta 是本次 chunk 生成的增量文本，可能为 None（比如第一个 chunk 只带 role 信息）
            delta = chunk.choices[0].delta
            # reasoning_content 是 DeepSeek 特有的字段，用于推理过程
            if getattr(delta, "reasoning_content", None):   # 换成 getattr
                yield {"type": "reasoning", "text": delta.reasoning_content}
            # content 是生成的文本内容
            if delta.content:
                yield {"type": "content", "text": delta.content}
    except Exception as e:
        # 两个位置可能到这里：create() 失败 / async for 中途断连。
        # 后者绝不能重试（用户已看到半个回答，重试会从头再来），统一发 error 事件
        yield {"type": "error", **translate(e).to_dict()}
