# -*- coding: utf-8 -*-
"""
n8n 服务封装 - 终极加固调试版
1. 解决 n8n 返回非 JSON 格式导致的程序崩溃
2. 增加原始响应日志，方便排查 Basic LLM Chain 的输出问题
3. 适配多种 n8n 返回结构 (List, Dict, 纯文本)
"""

import httpx
import json
from typing import Any, Literal, Optional, List, Dict
from loguru import logger
from pydantic import BaseModel, Field, ConfigDict


# ==================== 配置 ====================

class N8nConfig:
    # 🌟 n8n Webhook 基础地址
    WEBHOOK_BASE = "http://localhost:5678/webhook"

    # 超时配置
    TIMEOUT_SHORT = 45.0  # 蒸馏、分析等任务稍微加长一点
    TIMEOUT_LONG = 300.0  # 长文章生成

    # 重试配置
    MAX_RETRIES = 1


# ==================== 请求模型 ====================

class KeywordDistillRequest(BaseModel):
    keywords: List[str]
    project_id: Optional[int] = None


class GenerateQuestionsRequest(BaseModel):
    question: str
    count: int = 10


class GeoArticleRequest(BaseModel):
    keyword: str
    platform: str = "zhihu"
    requirements: str = ""
    word_count: int = 1200


class IndexCheckAnalysisRequest(BaseModel):
    keyword: str
    doubao_indexed: bool
    qianwen_indexed: bool
    deepseek_indexed: bool
    history: List[Dict] = []


# ==================== 响应模型 ====================

class N8nResponse(BaseModel):
    """n8n 统一响应格式"""
    status: Literal["success", "error", "processing"]
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ==================== 服务类 ====================

class N8nService:
    """
    n8n 服务类
    集成日志推送，支持自动化流水线的实时监控
    """

    def __init__(self, config: Optional[N8nConfig] = None):
        self.config = config or N8nConfig()
        # 🌟 绑定模块名，用于前端实时日志
        self.log = logger.bind(module="AI中台")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.config.TIMEOUT_SHORT,
                follow_redirects=True
            )
        return self._client

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _call_webhook(
            self,
            endpoint: str,
            payload: Dict[str, Any],
            timeout: Optional[float] = None
    ) -> N8nResponse:
        """底层统一调用逻辑"""
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        url = f"{self.config.WEBHOOK_BASE}{path}"
        timeout_val = timeout or self.config.TIMEOUT_SHORT

        self.log.info(f"🛰️ 正在外发 AI 请求: {endpoint}...")

        for attempt in range(self.config.MAX_RETRIES + 1):
            try:
                response = await self.client.post(url, json=payload, timeout=timeout_val)

                # 获取原始文本，这是调试的关键！
                raw_text = response.text

                # 1. 检查 HTTP 状态码
                if response.status_code != 200:
                    err_msg = f"HTTP {response.status_code}: {raw_text[:200]}"
                    self.log.error(f"❌ n8n 返回错误: {err_msg}")
                    return N8nResponse(status="error", error=err_msg)

                # 2. 尝试解析 JSON
                try:
                    res_data = response.json()

                    # 如果 n8n 返回的是数组格式（n8n 默认行为），取第一个
                    if isinstance(res_data, list):
                        res_data = res_data[0] if len(res_data) > 0 else {}

                    # 兼容性处理：如果返回结果里没有 status 字段，我们手动包装一层
                    if isinstance(res_data, dict) and "status" not in res_data:
                        return N8nResponse(status="success", data=res_data)

                    # 按照标准模型解析
                    return N8nResponse(**res_data)

                except json.JSONDecodeError:
                    # 🌟 报错现场捕捉：打印 n8n 吐出的真实内容
                    self.log.error(f"❌ n8n 响应不是有效的 JSON 格式！")
                    self.log.error(f"🔍 原始响应内容如下:\n{raw_text}")

                    # 特殊情况处理：如果 n8n 没配 Respond to Webhook，默认会返回 "Workflow started"
                    if "Workflow was started" in raw_text or "Workflow started" in raw_text:
                        return N8nResponse(status="error",
                                           error="n8n工作流缺少 'Respond to Webhook' 节点，无法接收AI数据")

                    return N8nResponse(status="error", error=f"JSON解析失败: {raw_text[:100]}")

            except httpx.TimeoutException:
                self.log.warning(f"⏳ 请求超时 (尝试 {attempt + 1}/{self.config.MAX_RETRIES + 1})")
                if attempt == self.config.MAX_RETRIES:
                    return N8nResponse(status="error", error="AI 生成超时，请检查 n8n 资源占用")

            except Exception as e:
                self.log.error(f"🚨 传输层异常: {str(e)}")
                return N8nResponse(status="error", error=str(e))

        return N8nResponse(status="error", error="未知错误")

    # ==================== 业务方法 ====================

    async def distill_keywords(self, keywords: List[str], project_id: Optional[int] = None) -> N8nResponse:
        """关键词蒸馏"""
        self.log.info(f"🧹 正在蒸馏提纯关键词...")
        payload = KeywordDistillRequest(keywords=keywords, project_id=project_id).model_dump()
        return await self._call_webhook("keyword-distill", payload)

    async def generate_questions(self, question: str, count: int = 10) -> N8nResponse:
        """生成问题变体"""
        self.log.info(f"❓ 正在基于原题扩展变体...")
        payload = GenerateQuestionsRequest(question=question, count=count).model_dump()
        return await self._call_webhook("generate-questions", payload)

    async def generate_geo_article(
            self,
            keyword: str,
            platform: str = "zhihu",
            requirements: str = "",
            word_count: int = 1200
    ) -> N8nResponse:
        """生成 GEO 优化文章 (长任务)"""
        self.log.info(f"📝 正在撰写适用于 [{platform}] 的 GEO 文章...")
        payload = GeoArticleRequest(
            keyword=keyword,
            platform=platform,
            requirements=requirements,
            word_count=word_count
        ).model_dump()

        return await self._call_webhook(
            "geo-article-generate",
            payload,
            timeout=self.config.TIMEOUT_LONG
        )

    async def analyze_index_check(
            self,
            keyword: str,
            doubao_indexed: bool,
            qianwen_indexed: bool,
            deepseek_indexed: bool,
            history: Optional[List[Dict]] = None
    ) -> N8nResponse:
        """分析收录结果"""
        self.log.info(f"📊 正在请求 AI 深度分析收录趋势...")
        payload = IndexCheckAnalysisRequest(
            keyword=keyword,
            doubao_indexed=doubao_indexed,
            qianwen_indexed=qianwen_indexed,
            deepseek_indexed=deepseek_indexed,
            history=history or []
        ).model_dump()
        return await self._call_webhook("index-check-analysis", payload)


# ==================== 单例模式 ====================

_instance: Optional[N8nService] = None


async def get_n8n_service() -> N8nService:
    global _instance
    if _instance is None:
        _instance = N8nService()
    return _instance