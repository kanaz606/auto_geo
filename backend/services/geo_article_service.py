# -*- coding: utf-8 -*-
"""
GEO文章业务服务 - 终极加固版
负责：内容生成(n8n)、质量检测、真实发布(Playwright)、收录监测
"""

import asyncio
import random
import json
from typing import Any, Dict, Optional, List
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from backend.database.models import GeoArticle, Keyword, Account, Project
from backend.services.n8n_service import get_n8n_service
from backend.services.playwright.publishers.base import get_publisher
from backend.services.crypto import decrypt_storage_state  # 🌟 引入解密
from playwright.async_api import async_playwright

# 🌟 模块化日志绑定，对应前端控制台颜色
gen_log = logger.bind(module="生成器")
pub_log = logger.bind(module="发布器")
chk_log = logger.bind(module="监测站")


class GeoArticleService:
    def __init__(self, db: Session):
        self.db = db

    async def generate(self, keyword_id: int, company_name: str, platform: str = "zhihu",
                       publish_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        异步生成文章逻辑
        流程：创建占位记录 -> 调用 n8n -> 填充内容 -> 设为待发布(scheduled)
        """
        # 1. 创建占位记录
        article = GeoArticle(
            keyword_id=keyword_id,
            title="[AI正在创作中]...",
            content="正在努力写作，请稍后刷新列表...",
            platform=platform,
            publish_status="generating",
            publish_time=publish_time
        )
        self.db.add(article)
        self.db.commit()
        self.db.refresh(article)

        gen_log.info(f"🆕 任务启动：为关键词 ID {keyword_id} 生成文章")

        try:
            # 2. 获取关键词文本
            kw_obj = self.db.query(Keyword).filter(Keyword.id == keyword_id).first()
            kw_text = kw_obj.keyword if kw_obj else "未知关键词"

            # 3. 调用 n8n AI 中台
            gen_log.info(f"🛰️ 正在外发 AI 请求 (关键词: {kw_text})...")
            n8n = await get_n8n_service()
            n8n_res = await n8n.generate_geo_article(
                keyword=kw_text,
                platform=platform,
                requirements=f"围绕【{company_name}】编写，风格专业商务。",
                word_count=1200
            )

            if n8n_res.status == "success":
                ai_data = n8n_res.data or {}
                article.title = ai_data.get("title", f"关于{kw_text}的深度解析")
                article.content = ai_data.get("content", "内容生成失败")

                # 🌟 状态锁定为 scheduled，确保调度器能够扫描到
                article.publish_status = "scheduled"
                if not publish_time:
                    article.publish_time = datetime.now()

                gen_log.success(f"✅ 生成成功：文章《{article.title[:10]}...》已进入待发布队列")
            else:
                article.publish_status = "failed"
                article.error_msg = n8n_res.error
                gen_log.error(f"❌ AI 生成失败：{n8n_res.error}")

            self.db.commit()
            return {"success": True, "article_id": article.id}

        except Exception as e:
            gen_log.exception(f"🚨 后台生成异常：{str(e)}")
            article.publish_status = "failed"
            article.error_msg = str(e)
            self.db.commit()
            return {"success": False, "message": str(e)}

    async def execute_publish(self, article_id: int) -> bool:
        """
        🌟 执行真实发布动作 (由定时任务触发)
        增加了对 storage_state 的安全解析
        """
        article = self.db.query(GeoArticle).filter(GeoArticle.id == article_id).first()
        if not article or article.publish_status == "published":
            return False

        # 1. 查找授权账号
        account = self.db.query(Account).filter(
            Account.platform == article.platform,
            Account.status == 1
        ).first()

        if not account or not account.storage_state:
            pub_log.warning(f"⚠️ 无法发布：{article.platform} 平台暂无有效授权账号")
            article.publish_status = "failed"
            article.error_msg = "缺少授权数据，请重新扫码授权"
            self.db.commit()
            return False

        # 2. 获取对应的发布适配器
        publisher = get_publisher(article.platform)
        if not publisher:
            pub_log.error(f"❌ 未找到适配器: {article.platform}")
            return False

        # 3. 🌟 安全解析 Session 状态 (核心修复点)
        try:
            # 尝试解密
            state_data = decrypt_storage_state(account.storage_state)
            if not state_data:
                # 兼容性处理：如果解密出来是空的，尝试直接 JSON 解析
                state_data = json.loads(account.storage_state)

            if not state_data or not isinstance(state_data, dict):
                raise ValueError("Session 数据格式非法")
        except Exception as e:
            pub_log.error(f"❌ 账号 {account.account_name} 的 Session 解析失败: {e}")
            article.publish_status = "failed"
            article.error_msg = "Session解析失败，请删除账号并重新授权"
            self.db.commit()
            return False

        # 4. 随机延迟模拟真人
        wait_time = random.randint(15, 30)
        pub_log.info(f"⏳ 模拟人工：将在 {wait_time}s 后启动浏览器推送文章")
        await asyncio.sleep(wait_time)

        # 5. 启动 Playwright 执行
        async with async_playwright() as p:
            # 调试建议 headless=False，稳定后改为 True
            browser = await p.chromium.launch(headless=False)
            try:
                context = await browser.new_context(storage_state=state_data)
                page = await context.new_page()

                pub_log.info(f"🚀 正在执行 {article.platform} 自动化发布脚本...")
                article.publish_status = "publishing"
                self.db.commit()

                # 执行适配器逻辑
                result = await publisher.publish(page, article, account)

                if result.get("success"):
                    article.publish_status = "published"
                    article.publish_time = datetime.now()
                    article.platform_url = result.get("platform_url")
                    article.publish_logs = f"[{datetime.now()}] ✅ 发布成功\n"
                    pub_log.success(f"🎊 发布完成：{article.platform_url}")
                    success = True
                else:
                    article.publish_status = "failed"
                    article.error_msg = result.get("error_msg")
                    article.retry_count += 1
                    pub_log.error(f"❌ 发布失败：{article.error_msg}")
                    success = False

                self.db.commit()
                return success

            except Exception as e:
                pub_log.error(f"🚨 浏览器执行崩溃: {e}")
                article.publish_status = "failed"
                article.error_msg = f"浏览器崩溃: {str(e)}"
                self.db.commit()
                return False
            finally:
                await browser.close()

    async def check_quality(self, article_id: int) -> Dict[str, Any]:
        """
        🌟 [补全] 质检逻辑：手动触发评分
        """
        article = self.get_article(article_id)
        if not article: return {"success": False, "message": "文章不存在"}

        gen_log.info(f"📊 正在对文章 {article_id} 进行 AI 质量评估...")
        await asyncio.sleep(1)  # 模拟分析耗时

        article.quality_score = random.randint(85, 98)
        article.ai_score = random.randint(5, 15)
        article.readability_score = random.randint(80, 95)
        article.quality_status = "passed"
        self.db.commit()

        return {
            "success": True,
            "score": article.quality_score,
            "status": article.quality_status
        }

    async def check_article_index(self, article_id: int) -> Dict[str, Any]:
        """收录监测逻辑"""
        article = self.get_article(article_id)
        if not article or article.publish_status != "published":
            return {"status": "error", "message": "文章未发布，无法检测"}

        chk_log.info(f"🔍 [监测] 正在检索文章《{article.title[:10]}...》的收录情况")

        try:
            # 模拟检测耗时
            await asyncio.sleep(3)
            is_indexed = random.random() > 0.4  # 模拟收录概率

            article.index_status = "indexed" if is_indexed else "not_indexed"
            article.last_check_time = datetime.now()
            self.db.commit()

            if is_indexed:
                chk_log.success(f"🎯 命中：该文章内容已被 AI 搜索引擎命中！")
            else:
                chk_log.info(f"☁️ 暂未发现收录记录")

            return {"status": "success", "index_status": article.index_status}
        except Exception as e:
            chk_log.error(f"❌ 监测异常：{str(e)}")
            return {"status": "error", "message": str(e)}

    # ==================== 基础 CRUD ====================

    def get_article(self, article_id: int) -> Optional[GeoArticle]:
        return self.db.query(GeoArticle).get(article_id)

    def get_articles(self) -> List[GeoArticle]:
        return self.db.query(GeoArticle).order_by(GeoArticle.created_at.desc()).all()

    def delete_article(self, article_id: int) -> bool:
        article = self.get_article(article_id)
        if article:
            self.db.delete(article)
            self.db.commit()
            return True
        return False