"""
公共层：chat.py 和 stream.py 共享的部分都在这里。

- AsyncOpenAI 客户端单例（「重」对象，内部维护 HTTP 连接池，只创建一次，所有请求复用）
- 消息格式与组装（build_messages）
- token 用量序列化（usage_to_dict）

分层规则：本文件只允许依赖 config，不允许 import 同包的 chat.py / stream.py，
否则会造成循环引用。
"""

"""公共层：Provider 配置、客户端工厂、消息组装。"""
from dataclasses import dataclass
import httpx                       # SDK 底层就是 httpx，直接用它的 Timeout

# 导入异步 OpenAI 客户端
from openai import AsyncOpenAI

# 导入配置
from services import config

# ---------------------------------------------------------------------------
# 1. 创建客户端
# ---------------------------------------------------------------------------
# AsyncOpenAI 是异步版本的客户端。因为我们的 FastAPI 服务是异步的（async def），
# 用异步客户端才不会在等待模型回复时阻塞整个服务。
# if not config.DEEPSEEK_API_KEY:
#     raise RuntimeError(
#         "未找到 DEEPSEEK_API_KEY。请在 backend/.env 中配置，例如：\n"
#         "DEEPSEEK_API_KEY=sk-xxxxxxxx"
#     )

# # 创建异步 OpenAI 客户端·
# client = AsyncOpenAI(
#     api_key=config.DEEPSEEK_API_KEY,
#     base_url=config.DEEPSEEK_BASE_URL,
# )

# ---------------------------------------------------------------------------
# 1. Provider 抽象：OpenAI 兼容服务的差异只有这三个字段，不配继承，配数据
# ---------------------------------------------------------------------------
@dataclass(frozen=True)             # frozen=True：配置不该被改，防止误操作
class ProviderConfig:
    name: str                       # "deepseek"，纯标识/日志用
    base_url: str
    api_key: str
    model: str

def default_provider() -> ProviderConfig:
    """从环境变量组装当前 provider。校验挪到这里：config 只读值，这里判「能不能用」。"""
    if not config.LLM_API_KEY:
        raise RuntimeError("未找到 LLM_API_KEY，请在 backend/.env 中配置")
    return ProviderConfig(
        name=config.LLM_PROVIDER,
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        model=config.LLM_MODEL,
    )
 
 
def create_client(p: ProviderConfig) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=p.api_key,
        base_url=p.base_url,
        # 两个旋钮：
        # timeout 用 httpx.Timeout 可以分开配——read=60 是「两个 chunk 之间的
        # 等待上限」，不是整个流的总时长，流式长回复不会误杀
        timeout=httpx.Timeout(connect=5.0, read=config.LLM_TIMEOUT, write=10.0, pool=10.0),
        # SDK 内置重试：对 429/5xx/超时自动指数退避，且尊重 Retry-After 响应头。
        # 401/400 它不会重试（不可重试错误 SDK 直接抛），正好符合我们的策略
        max_retries=config.LLM_MAX_RETRIES,
    )
 
 
# 单例：现有 chat.py/stream.py 继续用这个，先不改调用方式
provider = default_provider()
client = create_client(provider)

# ---------------------------------------------------------------------------
# 2. 消息格式与组装
# ---------------------------------------------------------------------------
# 大模型对话接口接收的不是一段字符串，而是一个「消息列表」，每条消息是一个字典：
#
#   {"role": "system",    "content": "你是一个..."}   # 系统提示：设定模型的身份和规则
#   {"role": "user",      "content": "你好"}          # 用户说的话
#   {"role": "assistant", "content": "你好！..."}     # 模型之前的回复
#
# 模型本身是「无状态」的——它不记得上一轮说过什么。
# 所谓「多轮对话」，其实是每次都把完整的历史消息列表重新发给它。
Message = dict[str, str]

# 默认的系统提示词。写在这里方便以后统一修改。
DEFAULT_SYSTEM_PROMPT = (
    "你是 DevSentinel 的智能助手，擅长帮助开发者诊断故障、分析日志和代码。"
    "回答要简洁、直接、有条理。"
)

# 未使用的历史对话记录版本
# def build_messages(user_message: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> list[Message]:
def build_messages(history: list[Message], system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> list[Message]:
    """
    组装发给模型的消息列表。

    现在只是 system + user 两条，看起来很简单；
    以后加多轮历史、工具结果、上下文压缩时，所有组装逻辑都集中在这一个函数里。
    """
    # return [
    #     {"role": "system", "content": system_prompt},
    #     {"role": "user", "content": user_message},
    # ]
    return [{"role": "system", "content": system_prompt}, *history]

def usage_to_dict(usage) -> dict | None:
    """
    把 SDK 的 usage 对象转成统一的字典。

    非流式的 response.usage 和流式结尾 chunk 的 chunk.usage 是同一个类型，
    所以这一个函数两边通用。返回 None 表示本次没有用量数据。
    """
    if usage is None:
        return None
    return {
        "prompt_tokens": usage.prompt_tokens,        # 输入消耗的 token
        "completion_tokens": usage.completion_tokens,  # 输出消耗的 token
        "total_tokens": usage.total_tokens,          # 两者之和
    }
