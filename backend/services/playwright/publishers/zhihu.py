# -*- coding: utf-8 -*-
"""
知乎发布适配器 - 修复版
增加了对“二次确认弹窗”的处理，确保能真正发出去！
"""

import asyncio
from typing import Dict, Any
from playwright.async_api import Page
from loguru import logger

from .base import BasePublisher, registry  # 确保导入 registry


class ZhihuPublisher(BasePublisher):
    """
    知乎发布适配器
    发布页面：https://zhuanlan.zhihu.com/write
    """

    # 选择器定义
    SELECTORS = {
        "title_input": "input[placeholder*='标题']",
        "content_editor": ".public-DraftStyleDefault-block",
        "publish_btn_1": "button:has-text('发布')",  # 顶部的发布按钮
        "publish_btn_2": "button:has-text('确认发布')",  # 弹窗里的确认按钮（关键！）
        "publish_btn_3": ".Modal button:has-text('发布')",  # 另一种弹窗按钮选择器
    }

    async def publish(self, page: Page, article: Any, account: Any) -> Dict[str, Any]:
        """发布文章到知乎"""
        try:
            logger.info("正在导航到知乎创作中心...")
            if not await self.navigate_to_publish_page(page):
                return {"success": False, "error_msg": "导航失败"}

            await asyncio.sleep(2)

            # 3. 填充标题
            if not await self._fill_title(page, article.title):
                return {"success": False, "error_msg": "标题填充失败"}

            # 4. 填充正文
            if not await self._fill_content(page, article.content):
                return {"success": False, "error_msg": "正文填充失败"}

            # 5. 点击发布（处理二次弹窗）
            logger.info("准备点击发布按钮...")
            if not await self._handle_publish_process(page):
                return {"success": False, "error_msg": "点击发布失败或超时"}

            # 6. 等待结果
            result = await self._wait_for_publish_result(page)
            return result

        except Exception as e:
            logger.exception(f"知乎发布脚本崩溃: {e}")
            return {"success": False, "error_msg": str(e)}

    async def _fill_title(self, page: Page, title: str) -> bool:
        """填充标题"""
        try:
            # 尝试多种选择器
            selectors = ["input[placeholder*='请输入标题']", "textarea[placeholder*='标题']", ".Input"]
            for sel in selectors:
                if await page.query_selector(sel):
                    await page.fill(sel, title)
                    logger.info("标题已填充")
                    return True
            return False
        except Exception as e:
            logger.error(f"标题填充错: {e}")
            return False

    async def _fill_content(self, page: Page, content: str) -> bool:
        """填充正文"""
        try:
            # 点击编辑器聚焦
            await page.click(".public-DraftEditor-content")
            await asyncio.sleep(0.5)

            # 使用剪贴板粘贴（比打字快且稳）- 需要浏览器权限，这里用 type 兜底
            # 或者简单的打字
            logger.info(f"正在输入正文... 长度: {len(content)}")
            # 只输入前 50 个字测试，或者全部输入
            # 为了演示效果，我们这里全部输入，但不用 type，太慢
            # 使用 evaluate 直接赋值可能会被 React 覆盖，所以还是用 press
            await page.keyboard.type(content)

            return True
        except Exception as e:
            logger.error(f"正文填充错: {e}")
            return False

    async def _handle_publish_process(self, page: Page) -> bool:
        """
        🌟 核心修复：处理发布流程中的连环点击
        """
        try:
            # 第一步：点击右上角的“发布”
            btn1 = await page.wait_for_selector("button:has-text('发布')", timeout=3000)
            if btn1:
                await btn1.click()
                logger.info("已点击右上角发布")
                await asyncio.sleep(1.5)  # 等待弹窗动画

            # 第二步：检查是否有“添加话题”的弹窗，需要再次点击确认
            # 知乎经常弹出一个框让你选话题，右下角有个“下一步”或者“发布”

            # 尝试找弹窗里的确认按钮
            confirm_selectors = [
                ".Modal button:has-text('发布')",  # 常见
                ".Modal button:has-text('确认发布')",  # 常见
                "button:has-text('下一步')",  # 有时候是下一步
            ]

            for sel in confirm_selectors:
                try:
                    btn2 = await page.query_selector(sel)
                    if btn2 and await btn2.is_visible():
                        await btn2.click()
                        logger.info(f"已点击弹窗确认按钮: {sel}")
                        await asyncio.sleep(1)
                        break
                except:
                    pass

            return True
        except Exception as e:
            logger.error(f"发布点击流程出错: {e}")
            return False

    async def _wait_for_publish_result(self, page: Page) -> Dict[str, Any]:
        """等待跳转成功"""
        logger.info("正在等待跳转至文章详情页...")
        try:
            # 等待 URL 变化，包含 /p/ 说明是文章页
            await page.wait_for_url("**/p/*", timeout=15000)

            return {
                "success": True,
                "platform_url": page.url,
                "error_msg": None
            }
        except Exception:
            # 如果超时没跳转，截图留证（实际开发中很有用）
            # await page.screenshot(path="debug_publish_fail.png")
            return {
                "success": False,
                "error_msg": "发布超时，未检测到成功跳转"
            }


# 配置
ZHIHU_CONFIG = {
    "name": "知乎",
    "publish_url": "https://zhuanlan.zhihu.com/write",
    "color": "#0084FF"
}

# 注册
registry.register("zhihu", ZhihuPublisher("zhihu", ZHIHU_CONFIG))