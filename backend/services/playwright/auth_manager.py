# -*- coding: utf-8 -*-
import asyncio
import json
from playwright.async_api import async_playwright
from loguru import logger


class AuthManager:
    def __init__(self, ws_callback=None):
        self.log = logger.bind(module="账号授权")
        self.ws_callback = ws_callback  # 用于向前端推送授权进度

    async def login_and_save_state(self, platform: str):
        """弹出浏览器，用户登录后保存 Session 状态"""
        urls = {
            "zhihu": "https://www.zhihu.com/signin",
            "baijiahao": "https://baijiahao.baidu.com/",
            "toutiao": "https://mp.toutiao.com/",
            "sohu": "https://mp.sohu.com/"
        }

        target_url = urls.get(platform)
        if not target_url:
            return {"status": "error", "message": "暂不支持该平台"}

        async with async_playwright() as p:
            # 必须开启 headless=False，否则用户没法扫码
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            self.log.info(f"正在打开 {platform} 登录页面...")
            await page.goto(target_url)

            # 轮询检查是否登录成功
            login_success = False
            try:
                # 给用户 2 分钟时间登录
                for _ in range(120):
                    await asyncio.sleep(2)
                    current_url = page.url

                    # 知乎登录成功的标志：进入首页或带有 'hot'
                    if platform == "zhihu" and ("zhihu.com/hot" in current_url or "zhihu.com/follow" in current_url):
                        login_success = True
                        break
                    # 其他平台的判断逻辑可以在此补充...
                    if platform == "toutiao" and "mp.toutiao.com/profile" in current_url:
                        login_success = True
                        break

                if login_success:
                    # 🌟 关键：保存整个存储状态（Cookies + LocalStorage）
                    state = await context.storage_state()
                    self.log.success(f"✅ {platform} 授权成功！")
                    return {"status": "success", "state": json.dumps(state)}
                else:
                    self.log.error("❌ 授权超时或被取消")
                    return {"status": "error", "message": "登录超时"}
            finally:
                await browser.close()