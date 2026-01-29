# -*- coding: utf-8 -*-
"""
Playwright 浏览器管理器 - 工业加固终极版 (v2.5)
负责：浏览器生命周期、账号授权、自动化发布、用户名提取
"""

import asyncio
import json
import os
import uuid
import inspect
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger
from sqlalchemy.orm import Session

# 内部导入
from backend.config import (
    BROWSER_TYPE, BROWSER_ARGS, PLATFORMS,
    LOGIN_CHECK_INTERVAL, LOGIN_MAX_WAIT_TIME
)
from backend.services.crypto import encrypt_cookies, encrypt_storage_state, decrypt_storage_state
from backend.services.playwright.publishers.base import registry

# 🌟 统一日志模块绑定
browser_log = logger.bind(module="浏览器")


class AuthTask:
    """授权任务模型"""

    def __init__(self, platform: str, account_id: Optional[int] = None, account_name: Optional[str] = None):
        self.task_id = str(uuid.uuid4().hex[:8])
        self.platform = platform
        self.account_id = account_id
        self.account_name = account_name
        self.status = "pending"  # pending, running, success, failed, timeout
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.cookies: List[Dict] = []
        self.storage_state: Dict = {}
        self.error_message: Optional[str] = None
        self.created_at = datetime.now()
        self.created_account_id: Optional[int] = None


class PlaywrightManager:
    """
    Playwright 管理器 (单例)
    """

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._auth_tasks: Dict[str, AuthTask] = {}
        self._contexts: Dict[str, BrowserContext] = {}
        self._is_running = False
        self._db_factory: Optional[Callable] = None
        self._ws_callback: Optional[Callable] = None

    def set_db_factory(self, db_factory: Callable):
        self._db_factory = db_factory

    def set_ws_callback(self, callback: Callable):
        self._ws_callback = callback

    def _get_db(self) -> Optional[Session]:
        """🌟 核心修复：兼容生成器和普通 Session 工厂"""
        if not self._db_factory:
            return None

        db_obj = self._db_factory()
        # 如果是 get_db 这种生成器，使用 next()
        if inspect.isgenerator(db_obj):
            return next(db_obj)
        # 否则直接返回（SessionLocal 情况）
        return db_obj

    async def start(self):
        """启动浏览器服务"""
        if self._is_running:
            return

        browser_log.info("🚀 正在初始化自动化浏览器核心...")
        self._playwright = await async_playwright().start()

        # 查找本地 Chrome 路径以绕过检测
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
        ]
        executable_path = next((p for p in chrome_paths if os.path.exists(p)), None)

        launch_options = {
            "headless": False,  # 授权时必须可见
            "args": BROWSER_ARGS + [
                "--disable-blink-features=AutomationControlled",  # 隐藏自动化特征
                "--no-sandbox"
            ]
        }
        if executable_path:
            launch_options["executable_path"] = executable_path

        self._browser = await self._playwright[BROWSER_TYPE].launch(**launch_options)
        self._is_running = True
        browser_log.success("✅ Playwright 浏览器服务已就绪")

    async def stop(self):
        """安全停止所有资源"""
        if not self._is_running: return
        for ctx in list(self._contexts.values()): await ctx.close()
        if self._browser: await self._browser.close()
        if self._playwright: await self._playwright.stop()
        self._is_running = False

    async def create_auth_task(self, platform: str, account_id: Optional[int] = None,
                               account_name: Optional[str] = None) -> AuthTask:
        """创建授权任务"""
        await self.start()
        if platform not in PLATFORMS: raise ValueError(f"暂不支持平台: {platform}")

        task = AuthTask(platform, account_id, account_name)
        self._auth_tasks[task.task_id] = task

        # 创建浏览器上下文
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        task.context = context

        # 注入 JS 桥接函数
        async def confirm_auth_wrapper(task_id: str) -> str:
            browser_log.info(f"收到授权确认信号: {task_id}")
            return await self._finalize_auth(task_id)

        await context.expose_function("confirmAuth", confirm_auth_wrapper)

        # 打开登录页
        login_page = await context.new_page()
        task.page = login_page
        await login_page.goto(PLATFORMS[platform]["login_url"], wait_until="domcontentloaded")

        # 打开本地控制页
        static_path = Path(__file__).parent.parent / "static" / "auth_confirm.html"
        if static_path.exists():
            control_page = await context.new_page()
            await control_page.goto(f"file:///{static_path.as_posix()}?task_id={task.task_id}&platform={platform}")

        task.status = "running"
        return task

    async def _finalize_auth(self, task_id: str) -> str:
        """核心：提取登录凭证并入库"""
        task = self._auth_tasks.get(task_id)
        if not task: return json.dumps({"success": False, "message": "任务已过期"})

        try:
            cookies = await task.context.cookies()
            # 基础验证
            is_valid = any(c['name'] == 'z_c0' for c in cookies) if task.platform == "zhihu" else len(cookies) > 5
            if not is_valid:
                return json.dumps({"success": False, "message": "检测到未登录，请完成登录后再试"})

            # 获取数据
            storage = await task.page.evaluate(
                "() => ({ localStorage: {...localStorage}, sessionStorage: {...sessionStorage} })")
            username = await self._extract_username(task.page, task.platform)

            db = self._get_db()
            if not db: return json.dumps({"success": False, "message": "数据库连接失败"})

            try:
                from backend.database.models import Account
                if task.account_id:
                    account = db.query(Account).get(task.account_id)
                else:
                    account = db.query(Account).filter(Account.platform == task.platform,
                                                       Account.username == username).first()
                    if not account:
                        account = Account(platform=task.platform,
                                          account_name=task.account_name or f"{task.platform}_{username}")
                        db.add(account)

                # 加密存储
                account.cookies = encrypt_cookies(cookies)
                account.storage_state = encrypt_storage_state({"cookies": cookies, "origins": []})
                account.username = username
                account.status = 1
                account.last_auth_time = datetime.now()

                db.commit()
                db.refresh(account)

                task.created_account_id = account.id
                task.status = "success"

                browser_log.success(f"🎉 账号 {username} 授权成功并已保存")

                if self._ws_callback:
                    await self._ws_callback({"type": "auth_complete", "task_id": task_id, "success": True})

                # 延时清理任务，给前端留出轮询时间
                asyncio.create_task(self._delayed_close_task(task_id))
                return json.dumps({"success": True, "message": "授权成功，请返回软件"})
            finally:
                db.close()
        except Exception as e:
            browser_log.error(f"授权入库失败: {e}")
            return json.dumps({"success": False, "message": str(e)})

    # 🌟 补全缺失的方法：供 account.py 调用
    def get_auth_task(self, task_id: str) -> Optional[AuthTask]:
        return self._auth_tasks.get(task_id)

    async def close_auth_task(self, task_id: str):
        task = self._auth_tasks.get(task_id)
        if task:
            if task.context: await task.context.close()
            if task_id in self._auth_tasks: del self._auth_tasks[task_id]
            browser_log.info(f"任务 {task_id} 资源已回收")

    async def _delayed_close_task(self, task_id: str):
        await asyncio.sleep(60)  # 保持60秒
        await self.close_auth_task(task_id)

    async def _extract_username(self, page: Page, platform: str) -> Optional[str]:
        """知乎用户名提取增强版"""
        try:
            if platform == "zhihu":
                selectors = [".AppHeader-profileText", ".Header-userName", ".UserLink-link", ".ProfileHeader-name"]
                for s in selectors:
                    el = await page.query_selector(s)
                    if el:
                        name = await el.text_content()
                        if name: return name.strip()
            return f"{platform}_User"
        except:
            return None

    # ==================== 真实发布入口 ====================
    async def execute_publish(self, article: Any, account: Any) -> Dict[str, Any]:
        """供 Service 调用的执行入口"""
        await self.start()
        publisher = registry.get(account.platform)
        if not publisher: return {"success": False, "error_msg": "适配器未注册"}

        # 🌟 加固：处理加密的 Session
        try:
            raw_state = decrypt_storage_state(account.storage_state)
            state_data = raw_state if raw_state else json.loads(account.storage_state)
        except:
            state_data = None

        context = await self._browser.new_context(storage_state=state_data)
        page = await context.new_page()
        try:
            return await publisher.publish(page, article, account)
        finally:
            await context.close()


# 单例
playwright_mgr = PlaywrightManager()