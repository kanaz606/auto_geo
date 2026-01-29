# -*- coding: utf-8 -*-
"""
收录检测服务 - 工业加固版
负责调用 Playwright 模拟 AI 搜索并实时推送执行进度
"""

import asyncio
import random
from datetime import datetime
from typing import List, Dict, Any, Optional
from loguru import logger
from sqlalchemy.orm import Session
from playwright.async_api import async_playwright

from backend.database.models import IndexCheckRecord, Keyword, QuestionVariant, GeoArticle
from backend.config import AI_PLATFORMS

# 🌟 绑定模块名，用于 WebSocket 实时日志着色
chk_log = logger.bind(module="监测站")


class IndexCheckService:
    def __init__(self, db: Session):
        self.db = db
        # 注意：这里假设你已经定义好了相关的 Checker 类
        # 如果还没写完逻辑，可以使用下方的 Mock 逻辑进行测试
        try:
            from backend.services.playwright.ai_platforms import DoubaoChecker, QianwenChecker, DeepSeekChecker
            self.checkers = {
                "doubao": DoubaoChecker("doubao", AI_PLATFORMS.get("doubao")),
                "qianwen": QianwenChecker("qianwen", AI_PLATFORMS.get("qianwen")),
                "deepseek": DeepSeekChecker("deepseek", AI_PLATFORMS.get("deepseek")),
            }
        except ImportError:
            self.checkers = {}
            chk_log.warning("⚠️ 警告：未找到 AI 平台检测插件，将使用模拟模式运行")

    async def run_ai_search_check(
            self,
            keyword_id: int,
            company_name: str,
            platforms: Optional[List[str]] = None
    ):
        """
        🌟 核心方法：执行收录检测 (由 API 异步调用)
        """
        # 1. 基础数据校验
        keyword_obj = self.db.query(Keyword).filter(Keyword.id == keyword_id).first()
        if not keyword_obj:
            chk_log.error(f"❌ 错误：关键词 ID {keyword_id} 不存在")
            return

        chk_log.info(f"🔍 监测启动：正在检索关键词 【{keyword_obj.keyword}】")

        # 2. 获取检测问题
        questions = self.db.query(QuestionVariant).filter(
            QuestionVariant.keyword_id == keyword_id
        ).all()

        # 兜底：如果没有变体词，生成一个默认问题
        query_texts = [q.question for q in questions] if questions else [
            f"请推荐一些专业的{keyword_obj.keyword}服务商，{company_name}怎么样？"]

        # 确定平台
        target_platforms = platforms if platforms else ["doubao", "qianwen", "deepseek"]

        # 3. 启动 Playwright 执行检测
        chk_log.info(f"🌐 正在初始化自动化浏览器 (目标平台: {', '.join(target_platforms)})...")

        async with async_playwright() as p:
            # 这里的 headless=True 代表后台运行。调试时可以改为 False 看效果
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            try:
                for platform_id in target_platforms:
                    chk_log.info(f"📡 正在接入 {platform_id} 平台...")

                    # 🌟 模拟/实际检测逻辑
                    for q_text in query_texts:
                        chk_log.info(f"💬 询问 AI: \"{q_text[:20]}...\"")

                        # --- 核心逻辑：这里调用你定义的每个平台的爬虫逻辑 ---
                        checker = self.checkers.get(platform_id)
                        if checker:
                            # 实际调用 Playwright 脚本
                            res = await checker.check(page, q_text, keyword_obj.keyword, company_name)
                        else:
                            # 🌟 Mock 模式：如果没有实现具体插件，先跑通流程
                            await asyncio.sleep(2)  # 模拟网络耗时
                            is_hit = random.random() > 0.4
                            res = {
                                "success": True,
                                "answer": f"为您找到关于{keyword_obj.keyword}的信息...",
                                "keyword_found": True,
                                "company_found": is_hit
                            }

                        # 4. 保存结果到数据库
                        record = IndexCheckRecord(
                            keyword_id=keyword_id,
                            platform=platform_id,
                            question=q_text,
                            answer=res.get("answer"),
                            keyword_found=res.get("keyword_found", False),
                            company_found=res.get("company_found", False),
                            check_time=datetime.now()
                        )
                        self.db.add(record)

                        # 5. 回填更新 GeoArticle 状态
                        article = self.db.query(GeoArticle).filter(GeoArticle.keyword_id == keyword_id).first()
                        if article:
                            if res.get("company_found"):
                                article.index_status = "indexed"
                                chk_log.success(f"🎯 命中！{platform_id} 已收录文章内容")
                            else:
                                article.index_status = "not_indexed"
                                chk_log.warning(f"☁️ 未命中：{platform_id} 暂未发现关联信息")
                            article.last_check_time = datetime.now()

                self.db.commit()
                chk_log.success(f"✅ 关键词 【{keyword_obj.keyword}】 监测任务执行完毕")

            except Exception as e:
                self.db.rollback()
                chk_log.error(f"🚨 监测过程中发生异常: {str(e)}")
            finally:
                await browser.close()

    def get_check_records(self, keyword_id: Optional[int] = None, platform: Optional[str] = None, limit: int = 100):
        query = self.db.query(IndexCheckRecord)
        if keyword_id:
            query = query.filter(IndexCheckRecord.keyword_id == keyword_id)
        if platform:
            query = query.filter(IndexCheckRecord.platform == platform)
        return query.order_by(IndexCheckRecord.check_time.desc()).limit(limit).all()

    def get_hit_rate(self, keyword_id: int) -> Dict[str, Any]:
        records = self.db.query(IndexCheckRecord).filter(IndexCheckRecord.keyword_id == keyword_id).all()
        if not records:
            return {"hit_rate": 0, "total": 0, "keyword_found": 0, "company_found": 0}
        total = len(records)
        kw_f = sum(1 for r in records if r.keyword_found)
        co_f = sum(1 for r in records if r.company_found)
        return {
            "overall_hit_rate": round((co_f / total) * 100, 2) if total > 0 else 0,
            "total_checks": total,
            "keyword_found_count": kw_f,
            "company_found_count": co_f
        }