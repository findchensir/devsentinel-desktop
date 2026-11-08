"""
llm 包：和大模型打交道的所有代码都收在这里。

分层：
- server.py        —— 接口层：只负责接收 HTTP 请求、返回响应，不关心模型细节。
- services/llm/client.py —— 公共层：SDK 客户端、消息组装、usage 序列化。
- services/llm/chat.py   —— 非流式对话。
- services/llm/stream.py —— 流式对话。

本文件是「门面」：对外只暴露 chat 和 chat_stream 两个函数，
server.py 用 `from services import llm` 导入后，llm.chat() / llm.chat_stream() 照常可用，
内部文件怎么拆分，接口层完全感知不到。

关于 DeepSeek 的 SDK：
DeepSeek 官方没有自己的 Python SDK，官方文档推荐直接使用 OpenAI 的 SDK，
因为 DeepSeek 的 API 和 OpenAI 的 Chat Completions 接口格式完全兼容。
"""

# 导入 chat、chat_stream、chat_structured 函数，供 server.py 使用
from .chat import chat, chat_structured
from .stream import chat_stream

__all__ = ["chat", "chat_stream", "chat_structured"]


# 该文件等价于js中的index.ts
# from .chat import chat    
# 等价于
# export { chat } from './chat'

# from .stream import chat_stream    
# 等价于
# export { chat_stream } from './stream'

# __all__ = ["chat", "chat_stream"]
# 等价于
# export { chat, chat_stream } from './chat' and './stream'