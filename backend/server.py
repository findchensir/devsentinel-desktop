import json
# 引入Python的异步库和FastAPI框架   
import asyncio
# 引入FastAPI框架  创建 Web API 服务
from fastapi import FastAPI
# 引入跨域中间件  允许前端访问后端API
from fastapi.middleware.cors import CORSMiddleware
# 引入StreamingResponse  用于流式响应，把响应内容分段发送，而不是等全部内容生成后才一次性返回
from fastapi.responses import StreamingResponse

# 引入Pydantic BaseModel  用于数据验证和序列化
from pydantic import BaseModel
# 引入HTTPException  用于非流式接口返回带状态码的错误
from fastapi import HTTPException
# 引入LLM模块，对应 backend/services/llm/（包），实际执行的是其中的 __init__.py
# 等价于 js 中的 import * as llm from './services/llm'
from services import llm
# 引入错误分类层：LLMError 用于按类型捕获，translate 用于兜底未知异常
from services.llm.errors import LLMError, translate

# 引入智能体模块
from services.agent import diagnose_workflow, agent_loop

# 引入LLM模型
from services.llm.models import FaultInfo


# | Python                      | JS                              | 使用方式              |
# |-----------------------------|---------------------------------|-----------------------|
# | `from services import llm`  | `import * as llm from './services/llm'` | `llm.chat()`          |
# | `from services.llm import chat` | `import { chat } from './services/llm'` | `chat()`              |
# | `import services.llm`       | `import './services/llm'` + 路径访问 | `services.llm.chat()` |
# | `from services import llm as l` | `import * as l from './services/llm'` | `l.chat()`            |


# 创建FastAPI应用实例，并设置标题为"DevSentinel Backend API"
app = FastAPI(title="DevSentinel Backend API")

app.add_middleware(
    # 添加跨域中间件  允许前端访问后端API
    CORSMiddleware,
    # 允许所有来源的请求  允许前端访问后端API
    allow_origins=["*"],
    # 允许携带凭证  允许前端访问后端API
    allow_credentials=True,
    # 允许所有HTTP方法  允许前端访问后端API
    allow_methods=["*"],
    # 允许所有HTTP头  允许前端访问后端API
    allow_headers=["*"],
)

# mock 流式响应
async def fake_agent_stream(prompt: str):
    response = f"【DevSentinel Agent】收到故障诊断请求：'{prompt}'。\n正在扫描本地 Git Commit 记录与系统日志...\n排查结论：检测到数据库连接池溢出，建议检查 Connection Limit 配置。"
    for char in response:
        # 使用yield关键字将每个字符作为数据流发送给客户端
        yield f"data: {char}\n\n"
        # 异步等待0.03秒，模拟处理时间，避免阻塞事件循环
        await asyncio.sleep(0.03)


# 定义一个GET请求的路由，路径为"/api/agent/diagnose"，用于处理故障诊断请求
@app.get("/api/agent/diagnose")
async def diagnose(prompt: str):
    # 返回StreamingResponse对象，将fake_agent_stream生成的流式响应发送给客户端，媒体类型为"text/event-stream"
    return StreamingResponse(fake_agent_stream(prompt), media_type="text/event-stream")


class ChatRequest(BaseModel):
    messages: list[dict]
    # 故障注入：联调前端错误态用。传 "rate_limit" 等 code 就直接返回对应错误，
    # 不用真把 DeepSeek 打挂
    mock_error: str | None = None
    stop: str | list[str] | None = None


# DeepSeek 流式响应
async def deepseek_sse_stream(req: ChatRequest):
    # ① 故障注入：伪造一个 error 事件 + [DONE]，走的协议和真实路径完全一致，
    #    前端拿到的数据结构没区别，可以放心联调 UI
    if req.mock_error:
        fake_err = {
            "type": "error",
            "code": req.mock_error,
            "message": f"模拟错误：{req.mock_error}",
            "retryable": True,
        }
        yield f"data: {json.dumps(fake_err, ensure_ascii=False)}\n\n"
        # yield "data: [DONE]\n\n"
        # DONE 事件化，保持与前端一致的事件类型
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        return

    # ② 正常路径：把 llm.chat_stream 吐出的事件原样包成 SSE 转发。
    #    注意 stream.py 内部已经把 SDK 异常翻译成了 error 事件，正常不会走到 except；
    #    这层兜底防的是 stream.py 自己的 bug 等漏网异常——SSE 永远正常收尾，不裸断
    try:
        async for event in llm.chat_stream(req.messages, stop=req.stop):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', **translate(e).to_dict()}, ensure_ascii=False)}\n\n"
    # 结束标记：让前端知道流结束了
    # yield "data: [DONE]\n\n"
    # DONE 事件化，保持与前端一致的事件类型
    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"


# 真实调用 DeepSeek 的流式接口。用法和 /api/agent/diagnose 一样，只是内容由模型生成。
@app.post("/api/agent/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(deepseek_sse_stream(req), media_type="text/event-stream")


# 非流式接口：和流式接口用同一个请求体，只是返回方式不同（JSON vs SSE）
@app.post("/api/agent/chat_once")
async def chat_once(req: ChatRequest):
    # 故障注入：非流式走 HTTP 状态码 + detail body，前端用 res.ok 分支处理
    if req.mock_error:
        raise HTTPException(status_code=500, detail={
            "code": req.mock_error,
            "message": f"模拟错误：{req.mock_error}",
            "retryable": True,
        })
    try:
        result = await llm.chat(req.messages)
    except LLMError as e:
        # LLMError 自带 http_status 和 to_dict()，一一映射成 HTTP 错误
        raise HTTPException(status_code=e.http_status, detail=e.to_dict())
    return {"answer": result["content"], "usage": result["usage"]}


# 结构化输出接口：模型返回 JSON → Pydantic 校验 → 失败重试，返回结构化数据
@app.post("/api/agent/diagnose_structured")
async def diagnose_structured(req: ChatRequest):
    try:
        result = await llm.chat_structured(req.messages)
    except Exception as e:
        # Pydantic 校验失败（重试用尽）或翻译后的 LLMError
        raise HTTPException(status_code=500, detail={
            "code": "structured_output_failed",
            "message": str(e),
            "retryable": True,
        })
    return {"data": result["data"], "usage": result["usage"]}

@app.post("/api/agent/extract_fault")
async def extract_fault(req: ChatRequest):
    try:
        result = await llm.chat_structured(
            req.messages,
            schema=FaultInfo,          # ← 同一个管道，换契约
            system_prompt="你是故障信息提取助手，将用户粘贴的报错信息提取为 JSON 结构化数据",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "code": "extract_failed",
            "message": str(e),
            "retryable": True,
        })
    return {"data": result["data"], "usage": result["usage"]}


# 值班助手 v0：固定工作流（提取 → grep 日志 → 总结），SSE 流式返回每步事件
@app.post("/api/agent/diagnose_workflow")
async def diagnose_wf(req: ChatRequest):
    # 取 messages 里最后一条 user 消息作为输入
    user_input = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")

    async def gen():
        try:
            async for event in diagnose_workflow(user_input):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', **translate(e).to_dict()}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# 手写 Agent 循环：模型自主决定调工具/何时停止，SSE 流式推送每步事件
@app.post("/api/agent/diagnose_agent")
async def diagnose_agent(req: ChatRequest):
    user_input = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")

    async def gen():
        try:
            async for event in agent_loop(user_input):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', **translate(e).to_dict()}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    # 使用uvicorn运行FastAPI应用，监听本地
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
