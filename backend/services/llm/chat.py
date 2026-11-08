"""
非流式对话：等模型生成完整回复后一次性返回。
"""

# from .client import ... 里的「.」表示「同一个包」，即 services/llm/ 目录下的 client.py。
# 包内部用相对导入，以后整个 llm/ 目录改名或移动时，内部引用不用改。

# 导入 DeepSeek 客户端、消息构建函数、默认系统提示词、usage 转字典工具
from .client import DEFAULT_SYSTEM_PROMPT, build_messages, client, usage_to_dict, provider

from .errors import translate

async def chat(history: list[dict], system_prompt: str = DEFAULT_SYSTEM_PROMPT, temperature: float = 0.3) -> dict:
    """
    等待模型生成完整回复后一次性返回。

    参数：
        history : 历史对话记录。
        system_prompt: 系统提示词，用来设定模型的角色。
        temperature: 温度参数，控制回复的创造性。

    返回：
        {"content": 模型回复文本, "usage": {prompt_tokens, ...} 或 None}
    """
    messages = build_messages(history, system_prompt)

    # chat.completions.create 是 OpenAI 兼容接口里「对话补全」的方法。
    # response = await client.chat.completions.create(
    #     model=config.DEEPSEEK_MODEL,
    #     messages=messages,
    #     temperature=temperature,
    # )

    try:
        response = await client.chat.completions.create(
            model=provider.model,
            messages=messages,
            temperature=temperature,
        )
    except Exception as e:
        raise translate(e)

    return {
        "content": response.choices[0].message.content or "",
        "usage": usage_to_dict(response.usage),
    }


# ---------------------------------------------------------------------------
# 结构化输出：让模型返回「能进程序的数据」，而不是给人看的文本
# ---------------------------------------------------------------------------
import json
from pydantic import BaseModel, ValidationError

from .models import DiagnosisResult


async def chat_structured(
    history: list[dict],
    schema: type[BaseModel] = DiagnosisResult,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    temperature: float = 0.3,
    max_retries: int = 2,
) -> dict:
    """
    结构化输出：模型返回 JSON → Pydantic 校验 → 失败带错误重试。

    为什么走非流式：JSON 只有生成完整才有意义，半截 JSON 无法解析。
    为什么校验后要重试：模型输出有随机性，偶尔字段名写错/类型不对，
    把错误塞回消息里让模型自我纠正，比直接报错好。

    返回：
        {"data": 校验后的 dict, "content": 原始 JSON 字符串, "usage": {...} 或 None}
    """
    # 每轮重试都基于「最新一份消息」，失败时 append assistant 的错误输出 + user 的纠正指令
    current_messages = history.copy()

    # system_prompt 里必须包含 "json"（DeepSeek 硬要求，否则直接 400）
    sp = system_prompt
    if "json" not in sp.lower():
        sp = sp + " 请以 JSON 格式输出。"

    for attempt in range(max_retries + 1):
        try:
            response = await client.chat.completions.create(
                model=provider.model,
                messages=build_messages(current_messages, sp),
                temperature=temperature,
                # response_format 告诉模型：返回的必须是合法 JSON。
                # 注意：它只保证「是 JSON」，不保证字段名/类型符合 schema，
                # 所以后面还要用 Pydantic 再做一遍语义校验。
                response_format={"type": "json_object"},
            )
        except Exception as e:
            raise translate(e)

        raw = response.choices[0].message.content or ""
        usage = usage_to_dict(response.usage)

        try:
            # Pydantic 校验：json.loads + 逐字段检查。
            # 字段名错、类型错、值域错（如 confidence>1）都会抛 ValidationError。
            data = schema.model_validate_json(raw).model_dump()
            return {"data": data, "content": raw, "usage": usage}

        except (ValidationError, json.JSONDecodeError) as e:
            if attempt == max_retries:
                # 重试次数用尽，把最后一次错误抛上去让调用方处理
                raise translate(e) if not isinstance(e, ValidationError) else e
            # 把模型的错误输出和校验失败原因塞回消息，让模型自我纠正
            current_messages = current_messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"输出不符合要求，错误：{e}。请重新按 JSON 格式输出。"},
            ]

    raise RuntimeError("chat_structured: 重试用尽仍未成功")
