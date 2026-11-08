"""错误分类层：把 SDK 五花八门的异常翻译成我们统一的 LLMError。

为什么需要它：上层（server/前端）不应该认识 openai SDK 的异常类型，
只认我们自己定义的 code 字符串。以后换 SDK 只改 translate() 一处。
"""
import openai


class LLMError(Exception):
    # 类属性 = 每种错误的「身份证」，子类只需要覆盖这三四个值
    code = "unknown"          # 机器可读，前端按它分支
    retryable = False         # 前端要不要显示「重试」按钮
    http_status = 502         # 非流式接口返回给前端的 HTTP 状态码

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code  # 上游原始状态码，日志用

    def to_dict(self) -> dict:
        # SSE error 事件和非流式 error body 都用它序列化，保证两处协议一致
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


class AuthError(LLMError):
    code, retryable, http_status = "auth", False, 401
    # message 在翻译时给："API Key 无效或未配置"


class RateLimitError(LLMError):
    code, retryable, http_status = "rate_limit", True, 429


class UpstreamError(LLMError):
    code, retryable, http_status = "upstream", True, 502


class LLMTimeoutError(LLMError):
    code, retryable, http_status = "timeout", True, 504


class ConnectionFailed(LLMError):
    code, retryable, http_status = "connection", True, 503


class LLMBadRequestError(LLMError):
    code, retryable, http_status = "bad_request", False, 400
    # 比如 context_length_exceeded——请求本身有问题，重试无意义


# 映射表：(SDK 异常类型, 我们的错误类, 文案)。注意顺序——
# SDK 的异常有继承关系，AuthenticationError 是 APIStatusError 的子类，
# 所以更具体的类型必须放前面先匹配（想想如果把 APIStatusError 放第一行会怎样？）
# 由子类到父类，按继承关系从上到下排列，越具体的异常越靠前
_ERROR_MAP = [
    (openai.AuthenticationError,  AuthError,         "API Key 无效，请检查 .env 配置"),
    (openai.PermissionDeniedError, AuthError,        "没有访问权限"),
    (openai.RateLimitError,       RateLimitError,    "请求太频繁，请稍后重试"),
    (openai.APITimeoutError,      LLMTimeoutError,   "模型响应超时"),
    (openai.APIConnectionError,   ConnectionFailed,  "无法连接到模型服务，检查网络或 base_url"),
    (openai.BadRequestError,      LLMBadRequestError, "请求参数有误"),
    (openai.APIStatusError,       UpstreamError,     "模型服务暂时不可用"),
    (TimeoutError,                LLMTimeoutError,   "模型响应超时"),  # asyncio.wait_for 抛的
]


def translate(exc: Exception) -> LLMError:
    """把任意异常翻译成 LLMError。已是 LLMError 的原样返回（幂等）。"""
    if isinstance(exc, LLMError):
        return exc
    for exc_type, err_cls, msg in _ERROR_MAP:
        if isinstance(exc, exc_type):
            return err_cls(msg, status_code=getattr(exc, "status_code", None))
    return LLMError(f"未知错误：{exc}")