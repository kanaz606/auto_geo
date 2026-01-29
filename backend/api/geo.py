# -*- coding: utf-8 -*-
"""
GEO文章管理 API - 工业加固版
处理文章生成、质检、列表、收录检测触发等
"""

from typing import List, Optional, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.database import get_db, SessionLocal
from backend.services.geo_article_service import GeoArticleService
from backend.database.models import GeoArticle, Project
from backend.schemas import ApiResponse
from loguru import logger

router = APIRouter(prefix="/api/geo", tags=["GEO文章"])


# ==================== 请求/响应模型 ====================

class GenerateArticleRequest(BaseModel):
    """文章生成请求模型"""
    keyword_id: int
    company_name: str
    platform: str = "zhihu"
    publish_time: Optional[datetime] = None


class ArticleResponse(BaseModel):
    """
    🌟 核心模型：解决前端列表显示的所有字段需求
    """
    id: int
    keyword_id: int
    title: Optional[str] = None
    content: Optional[str] = None

    # 状态字段
    quality_status: Optional[str] = "pending"
    publish_status: Optional[str] = "draft"
    index_status: Optional[str] = "uncheck"
    platform: Optional[str] = "zhihu"

    # 评分字段
    quality_score: Optional[int] = None
    ai_score: Optional[int] = None
    readability_score: Optional[int] = None

    # 记录与日志
    retry_count: Optional[int] = 0
    error_msg: Optional[str] = None
    publish_logs: Optional[str] = None
    platform_url: Optional[str] = None  # 🌟 发布成功后的真实链接
    index_details: Optional[str] = None

    # 时间戳
    publish_time: Optional[datetime] = None
    last_check_time: Optional[datetime] = None
    created_at: Optional[datetime] = None

    # 兼容 SQLAlchemy 对象
    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(BaseModel):
    id: int
    name: str
    company_name: str
    model_config = ConfigDict(from_attributes=True)


# ==================== 异步辅助逻辑 ====================

async def run_generate_task(keyword_id: int, company_name: str, platform: str, publish_time: Optional[datetime]):
    """后台执行生成任务的闭包"""
    db = SessionLocal()
    try:
        service = GeoArticleService(db)
        await service.generate(keyword_id, company_name, platform, publish_time)
    except Exception as e:
        logger.error(f"❌ 后台生成任务失败: {str(e)}")
    finally:
        db.close()


# ==================== 接口实现 ====================

@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(db: Session = Depends(get_db)):
    """获取所有活跃项目列表"""
    return db.query(Project).filter(Project.status == 1).all()


@router.post("/generate", response_model=ApiResponse)
async def generate_article(request: GenerateArticleRequest, background_tasks: BackgroundTasks):
    """
    提交文章生成任务
    使用 BackgroundTasks 实现非阻塞响应
    """
    background_tasks.add_task(
        run_generate_task,
        request.keyword_id,
        request.company_name,
        request.platform,
        request.publish_time
    )
    return ApiResponse(success=True, message="生成任务已提交，请在列表查看进度")


@router.get("/articles", response_model=List[ArticleResponse])
async def list_articles(limit: int = Query(100), db: Session = Depends(get_db)):
    """获取文章列表（按创建时间倒序）"""
    articles = db.query(GeoArticle).order_by(desc(GeoArticle.created_at)).limit(limit).all()
    return articles


@router.post("/articles/{article_id}/check-quality", response_model=ApiResponse)
async def check_quality(article_id: int, db: Session = Depends(get_db)):
    """
    🌟 [修复] 手动触发文章质检评分
    """
    service = GeoArticleService(db)
    try:
        result = await service.check_quality(article_id)
        if result.get("success"):
            return ApiResponse(success=True, message="质检完成", data=result)
        return ApiResponse(success=False, message=result.get("message", "质检失败"))
    except Exception as e:
        logger.error(f"质检异常: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/articles/{article_id}/check-index", response_model=ApiResponse)
async def manual_check_index(article_id: int, db: Session = Depends(get_db)):
    """手动触发单篇文章的收录监测"""
    service = GeoArticleService(db)
    try:
        result = await service.check_article_index(article_id)
        if result.get("status") == "error":
            return ApiResponse(success=False, message=result.get("message"))
        return ApiResponse(success=True, message=f"检测完成，当前状态：{result.get('index_status')}")
    except Exception as e:
        logger.error(f"收录检测异常: {str(e)}")
        return ApiResponse(success=False, message="检测服务暂时不可用")


@router.delete("/articles/{article_id}", response_model=ApiResponse)
async def delete_article(article_id: int, db: Session = Depends(get_db)):
    """删除文章记录"""
    article = db.query(GeoArticle).filter(GeoArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    try:
        db.delete(article)
        db.commit()
        return ApiResponse(success=True, message="文章已成功删除")
    except Exception as e:
        db.rollback()
        return ApiResponse(success=False, message=f"删除失败: {str(e)}")