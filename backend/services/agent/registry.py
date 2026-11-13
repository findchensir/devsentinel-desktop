"""工具注册表：把 Python 函数变成"模型可调用的工具"。

三件套：
1. 参数模型（Pydantic）：既是入参校验器，又自动生成 JSON Schema
2. TOOL_REGISTRY：工具名 → {函数, 参数模型, 描述}
3. call_tool：按名字分发调用，把"模型给的 JSON"翻译成 Python 调用

模型侧只看到 tool_schemas() 输出的说明书；执行侧只调 call_tool()。
新增工具 = 写一个函数 + 一个 Args 模型 + 注册一行。
"""
from pydantic import BaseModel, Field, ValidationError

from .tools import read_log, search_code, git_log, git_show


# ---------- 参数模型：描述就是给模型看的工具说明 ----------

class ReadLogArgs(BaseModel):
    """read_log 的入参：按服务/时间窗/关键词过滤日志。"""
    service: str = Field(
        default="",
        description="服务名，对应日志文件名（如 order-service）。留空则搜索全部日志",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="日志检索关键词，输出日志里可能出现的英文术语/错误片段（如 timeout、total=、ERROR）。留空返回时间窗内全部行",
    )
    start: str = Field(
        default="",
        description="时间窗起点，如 '15:00' 或 '2026-11-08 15:00:11'。留空不限",
    )
    end: str = Field(
        default="",
        description="时间窗终点，格式同 start。留空不限",
    )
    max_lines: int = Field(
        default=50,
        description="最多返回多少行，防止超长输出爆上下文",
    )


class SearchCodeArgs(BaseModel):
    """search_code 的入参：在服务源码里搜字符串。"""
    query: str = Field(
        description="搜索词：函数名、变量名、常量名或代码片段（如 POOL_MAX、dec_stock、while True）",
    )
    max_lines: int = Field(
        default=30,
        description="最多返回多少行片段",
    )


class GitLogArgs(BaseModel):
    """git_log 的入参：看最近提交历史。"""
    max_count: int = Field(default=10, description="最多看几条提交，默认 10")


class GitShowArgs(BaseModel):
    """git_show 的入参：看某次提交的具体改动。"""
    commit: str = Field(description="commit hash，如 783f100（可从 git_log 结果获取）")
    max_lines: int = Field(default=80, description="最多返回多少行 diff")


# ---------- 注册表 ----------

TOOL_REGISTRY: dict[str, dict] = {
    "read_log": {
        "func": read_log,
        "args_model": ReadLogArgs,
        "description": "按服务名/时间窗/关键词过滤日志，返回命中片段（含来源文件标注）。排查日志证据用",
    },
    "search_code": {
        "func": search_code,
        "args_model": SearchCodeArgs,
        "description": "在服务源码中搜索字符串，返回 文件:行号 + 上下文片段。定位代码证据/根因位置用",
    },
    "git_log": {
        "func": git_log,
        "args_model": GitLogArgs,
        "description": "查看靶场仓库最近的提交历史（hash + 提交信息）。当日志/代码无法解释故障、怀疑是最近变更引入时用",
    },
    "git_show": {
        "func": git_show,
        "args_model": GitShowArgs,
        "description": "查看某次提交的完整 diff。用 git_log 找到可疑提交后，用它确认具体改了哪行",
    },
}


def tool_schemas() -> list[dict]:
    """生成 OpenAI tools 参数格式的 schema 列表，直接喂给 chat.completions 的 tools=。"""
    schemas = []
    for name, spec in TOOL_REGISTRY.items():
        params = spec["args_model"].model_json_schema()
        # model_json_schema 会带 $defs/title 等，OpenAI 只要 properties/required
        schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": params,
            },
        })
    return schemas


def call_tool(name: str, arguments: dict) -> str:
    """按名字分发调用工具。

    返回值永远是字符串——成功是结果，失败是给模型的错误提示。
    不抛异常：错误要喂回模型让它修正参数重试，异常会中断 Agent 循环。
    """
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return f"[错误] 未知工具: {name}。可用工具: {', '.join(TOOL_REGISTRY)}"

    if not isinstance(arguments, dict):
        return f"[错误] arguments 必须是 JSON 对象，收到: {type(arguments).__name__}"

    try:
        args = spec["args_model"].model_validate(arguments)
    except ValidationError as e:
        # 把校验错误压缩成模型能看懂的一行提示
        problems = "; ".join(
            f"{'.'.join(str(l) for l in err['loc'])}: {err['msg']}" for err in e.errors()
        )
        return f"[错误] 参数校验失败: {problems}。请修正后重试"

    try:
        return spec["func"](**args.model_dump())
    except Exception as e:
        return f"[错误] 工具执行异常: {type(e).__name__}: {e}"
