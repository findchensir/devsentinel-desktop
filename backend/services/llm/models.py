"""
结构化输出的数据契约：模型返回的 JSON 必须长这个样。

为什么用 Pydantic 定义：
- 它同时是「文档」（模型要返回什么）和「闸门」（不合法就拒绝进入下游）
- Field(ge=0, le=1) 这类约束不只是查类型，还查值的合法范围
"""
from pydantic import BaseModel, Field

# 类型别名，用于枚举类型
from typing import Literal

class DiagnosisResult(BaseModel):
    """诊断结果的结构化输出"""

    root_cause: str = Field(description="根因的一句话描述")
    confidence: float = Field(ge=0, le=1, description="置信度，0-1 之间")
    evidence: list[str] = Field(description="支撑结论的证据列表")
    suggested_actions: list[str] = Field(description="建议的修复动作")



class FaultInfo(BaseModel):
    """从用户粘贴的报错信息中提取的结构化故障要素"""
    service: str = Field(description="故障服务名，如 order-service")
    error_type: str = Field(description="错误类型，如 timeout / 5xx / oom")
    severity: Literal["low", "medium", "high", "critical"] = Field(description="严重级别")
    keywords: list[str] = Field(description="关键特征词，用于后续检索")