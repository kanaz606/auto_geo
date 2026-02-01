# -*- coding: utf-8 -*-
"""
知乎发布适配器 - v4.1 多图流排版版
核心升级：
1. 支持多张图片依次插入，不再仅限首图
2. 模拟“翻页 -> 换行 -> 粘贴”的排版逻辑，使图片分布在文章不同位置
3. 保持强制配图和封面上传的稳定性
"""

import asyncio
import re
import os
import httpx
import tempfile
import base64
import random
import urllib.parse
from typing import Dict, Any, List, Optional
from playwright.async_api import Page
from loguru import logger

from .base import BasePublisher, registry


class ZhihuPublisher(BasePublisher):
    async def publish(self, page: Page, article: Any, account: Any) -> Dict[str, Any]:
        temp_files = []
        try:
            logger.info("🚀 开始知乎发布 (v4.1 多图流排版版)...")

            # 1. 导航
            await page.goto(self.config["publish_url"], wait_until="networkidle", timeout=60000)
            await asyncio.sleep(5)

            # 2. 图像准备
            # A. 提取正文链接
            image_urls = re.findall(r'!\[.*?\]\(((?:https?://)?\S+?)\)', article.content)
            # B. 清洗正文
            clean_content = re.sub(r'!\[.*?\]\(.*?\)', '', article.content)

            # C. 强制补图策略
            if not image_urls:
                keyword = article.title[:10] if article.title else "technology"
                # 生成3张不同的图，确保文章丰富度
                for i in range(3):
                    seed = random.randint(1, 1000)
                    encoded_kw = urllib.parse.quote(f"high quality realistic photo of {keyword} {seed}")
                    url = f"https://image.pollinations.ai/prompt/{encoded_kw}?width=800&height=600&nologo=true"
                    image_urls.append(url)
                logger.info(f"🎨 已自动生成 {len(image_urls)} 张配图链接")

            # D. 下载图片
            downloaded_paths = await self._download_images(image_urls)
            temp_files.extend(downloaded_paths)

            if not downloaded_paths:
                return {"success": False, "error_msg": "图片下载失败，无法满足强制配图需求"}

            # 3. 填充标题
            await self._fill_title(page, article.title)

            # 4. 填充正文
            await self._fill_content_and_clean_ui(page, clean_content)

            # 5. 🌟 执行多图排版上传
            await self._handle_multi_image_upload(page, downloaded_paths)

            # 6. 发布流程
            topic_word = getattr(article, 'keyword_text', article.title[:4])
            if not await self._handle_publish_process(page, topic_word):
                return {"success": False, "error_msg": "发布确认环节失败"}

            return await self._wait_for_publish_result(page)

        except Exception as e:
            logger.exception(f"❌ 知乎脚本致命故障: {str(e)}")
            return {"success": False, "error_msg": str(e)}
        finally:
            for f in temp_files:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except:
                        pass

    async def _download_images(self, urls: List[str]) -> List[str]:
        paths = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient(headers=headers, verify=False, follow_redirects=True) as client:
            # 下载前 3 张
            for i, url in enumerate(urls[:3]):
                for attempt in range(2):
                    try:
                        resp = await client.get(url, timeout=20.0)
                        if resp.status_code == 200:
                            if len(resp.content) < 1000: continue
                            tmp_path = os.path.join(tempfile.gettempdir(), f"zh_v41_{random.randint(1000, 9999)}.jpg")
                            with open(tmp_path, "wb") as f:
                                f.write(resp.content)
                            paths.append(tmp_path)
                            logger.info(f"✅ 图片 {i + 1} 下载成功")
                            break
                    except:
                        pass
        return paths

    async def _handle_multi_image_upload(self, page: Page, paths: List[str]):
        """
        多图排版逻辑：
        1. 第一张设为封面 + 插入文章顶部
        2. 后续图片插入文章中间或底部
        """
        try:
            # Step 1: 上传封面 (使用第一张图)
            logger.info("🖼️ 正在设置文章封面...")
            cover_input = page.locator("input.UploadPicture-input").first
            if await cover_input.count() > 0:
                await cover_input.set_input_files(paths[0])
                await asyncio.sleep(3)

            # Step 2: 遍历插入正文
            editor = page.locator(".public-DraftEditor-content").first
            await editor.click()

            for i, image_path in enumerate(paths):
                logger.info(f"📝 正在插入第 {i + 1}/{len(paths)} 张图片...")

                if i == 0:
                    # 第一张：回到顶部插入
                    await page.keyboard.press("Control+Home")
                    await page.keyboard.press("Enter")
                    await page.keyboard.press("ArrowUp")
                else:
                    # 后续图片：模拟向下阅读翻页，然后插入
                    # 按 4 次 PageDown (约往下翻 2-3 屏)
                    for _ in range(4):
                        await page.keyboard.press("PageDown")
                        await asyncio.sleep(0.2)

                    # 回车换行，腾出空间
                    await page.keyboard.press("Enter")

                # 执行粘贴注入
                await self._paste_image_via_js(page, image_path)

                # 等待上传完成，避免并发冲突
                await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"多图上传流程部分失败: {e}")

    async def _paste_image_via_js(self, page: Page, image_path: str):
        """通用粘贴函数：读取本地图片并伪造 Paste 事件"""
        with open(image_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode('utf-8')

        await page.evaluate('''(data) => {
            const { b64 } = data;
            const byteCharacters = atob(b64);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);
            const blob = new Blob([byteArray], { type: 'image/jpeg' });
            const file = new File([blob], "auto_inserted.jpg", { type: 'image/jpeg' });

            const dt = new DataTransfer();
            dt.items.add(file);

            const editor = document.querySelector(".public-DraftEditor-content");
            const event = new ClipboardEvent("paste", {
                clipboardData: dt,
                bubbles: true,
                cancelable: true
            });
            editor.dispatchEvent(event);
        }''', {"b64": b64_data})

    async def _fill_title(self, page: Page, title: str):
        sel = "input[placeholder*='标题'], .WriteIndex-titleInput textarea"
        await page.wait_for_selector(sel)
        await page.fill(sel, title)

    async def _fill_content_and_clean_ui(self, page: Page, content: str):
        editor = ".public-DraftEditor-content"
        await page.wait_for_selector(editor)
        await page.click(editor)

        await page.evaluate('''(text) => {
            const dt = new DataTransfer();
            dt.setData("text/plain", text);
            const ev = new ClipboardEvent("paste", { clipboardData: dt, bubbles: true });
            document.querySelector(".public-DraftEditor-content").dispatchEvent(ev);
        }''', content)

        await asyncio.sleep(2)
        try:
            confirm = page.locator("button:has-text('确认并解析')").first
            if await confirm.is_visible(timeout=3000):
                await confirm.click()
        except:
            pass

    async def _handle_publish_process(self, page: Page, topic: str) -> bool:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            add_topic = page.locator("button:has-text('添加话题')").first
            if await add_topic.is_visible(timeout=2000):
                await add_topic.click()

            topic_input = page.locator("input[placeholder*='话题']").first
            await topic_input.fill(topic)
            await asyncio.sleep(2)
            suggestion = page.locator(".Suggestion-item, .PublishPanel-suggestionItem").first
            if await suggestion.is_visible(timeout=2000):
                await suggestion.click()
            else:
                await page.keyboard.press("Enter")
        except:
            pass

        final_btn = page.locator(
            "button.PublishPanel-submitButton, .WriteIndex-publishButton, button:has-text('发布')").last
        for _ in range(5):
            if await final_btn.is_enabled():
                await final_btn.click(force=True)
                return True
            await asyncio.sleep(2)
        return False

    async def _wait_for_publish_result(self, page: Page) -> Dict[str, Any]:
        for i in range(25):
            if "/p/" in page.url and "/edit" not in page.url:
                return {"success": True, "platform_url": page.url}
            await asyncio.sleep(1)
        return {"success": False, "error_msg": "发布超时"}


# 注册
ZHIHU_CONFIG = {"name": "知乎", "publish_url": "https://zhuanlan.zhihu.com/write", "color": "#0084FF"}
registry.register("zhihu", ZhihuPublisher("zhihu", ZHIHU_CONFIG))
