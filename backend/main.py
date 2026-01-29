# -*- coding: utf-8 -*-
"""
AutoGeo 后端服务入口 - 工业加固版
"""

import sys
import os
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List
import uuid

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# 导入内部组件
from backend.services.websocket_manager import ws_manager
from backend.config import (
    APP_NAME, APP_VERSION, DEBUG, HOST, PORT, RELOAD,
    CORS_ORIGINS, PLATFORMS
)
from backend.database import init_db, get_db, SessionLocal
from backend.api import (
    account, article, publish, keywords, geo,
    index_check, reports, notifications, scheduler, knowledge
)
from backend.services.scheduler_service import get_scheduler_service
from backend.services.n8n_service import get_n8n_service


# ==================== 🌟 日志拦截器 (优化版) ====================

def socket_log_sink(message):
    """
    Loguru 拦截器：将每一条日志通过 WebSocket 广播出去
    """
    try:
        record = message.record
        # 构造发送给前端的标准 JSON 格式
        log_payload = {
            "time": record["time"].strftime("%H:%M:%S"),
            "level": record["level"].name,
            "module": record["extra"].get("module", "系统"),
            "message": record["message"],
        }

        # 获取当前运行的事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(ws_manager.broadcast(log_payload))
        except RuntimeError:
            # 如果当前线程没有运行中的 loop，则忽略（通常发生在关闭阶段）
            pass
    except Exception:
        pass


# 配置 Loguru
logger.remove()
logger.add(sys.stdout, level="INFO", colorize=True)
logger.add(socket_log_sink, level="INFO")


# ==================== 应用生命周期管理 ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理：处理启动时的初始化和关闭时的资源释放
    """
    # ---------------- 启动阶段 ----------------
    logger.info(f"🚀 {APP_NAME} v{APP_VERSION} 正在启动...")

    # 1. 初始化数据库 (WAL模式)
    try:
        init_db()
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")

    # 2. 注入全局 WebSocket 管理器
    account.set_ws_manager(ws_manager)
    publish.set_ws_manager(ws_manager)
    notifications.set_ws_callback(ws_manager.broadcast)

    # 3. 初始化 Playwright 管理器
    from backend.services.playwright_mgr import playwright_mgr
    # 🌟 关键修复：使用 SessionLocal 而不是 get_db
    # SessionLocal() 会直接返回 Session 对象，而 get_db() 返回的是生成器
    playwright_mgr.set_db_factory(SessionLocal)
    playwright_mgr.set_ws_callback(ws_manager.broadcast)

    # 4. 启动定时任务引擎
    scheduler_instance = get_scheduler_service()
    scheduler_instance.set_db_factory(SessionLocal)
    scheduler_instance.start()

    logger.bind(module="调度中心").success("自动化任务引擎已启动")

    yield

    # ---------------- 关闭阶段 ----------------
    logger.info("正在关闭服务，释放资源...")

    # 停止定时任务
    scheduler_instance.stop()

    # 关闭 Playwright
    await playwright_mgr.stop()

    # 关闭 n8n HTTP 客户端连接
    n8n_service = await get_n8n_service()
    await n8n_service.close()

    logger.info("服务已安全关闭")


# ==================== 创建应用实例 ====================
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    debug=DEBUG,
    lifespan=lifespan
)

# 跨域中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由 - 请确保 reports.router 在 index_check 之后，或者前缀区分明确
app.include_router(account.router)
app.include_router(article.router)
app.include_router(publish.router)
app.include_router(keywords.router)
app.include_router(geo.router)
app.include_router(index_check.router)  # 前缀 /api/index-check
app.include_router(reports.router)  # 前缀 /api/reports
app.include_router(notifications.router)
app.include_router(scheduler.router)
app.include_router(knowledge.router)


# ==================== WebSocket 端点 ====================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, client_id: str = None):
    """
    实时日志 WebSocket 通道
    """
    if not client_id:
        client_id = f"client_{uuid.uuid4().hex[:8]}"

    await ws_manager.connect(websocket, client_id)

    # 发送连接成功的初始信号
    await ws_manager.send_personal({
        "time": "系统",
        "level": "SUCCESS",
        "module": "系统",
        "message": "实时监控链路已就绪"
    }, client_id)

    try:
        while True:
            # 保持连接，接收客户端心跳（如有）
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}")
        ws_manager.disconnect(client_id)


# ==================== 基础健康检查 ====================
@app.get("/")
async def root():
    return {"app": APP_NAME, "version": APP_VERSION, "status": "running"}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ==================== 启动脚本 ====================
if __name__ == "__main__":
    import uvicorn

    # Windows 下异步策略优化
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=RELOAD,
        log_level="info"
    )