# -*- coding: utf-8 -*-
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Integer
from backend.database import get_db
from backend.database.models import Project, Keyword, IndexCheckRecord, GeoArticle

router = APIRouter(prefix="/api/reports", tags=["数据报表"])


class TrendDataPoint(BaseModel):
    date: str
    keyword_found_count: int
    total_checks: int


@router.get("/overview")
async def get_overview(db: Session = Depends(get_db)):
    """获取顶部统计卡片"""
    # 统计监测记录表
    total_checks = db.query(IndexCheckRecord).count()

    if total_checks == 0:
        return {
            "total_projects": db.query(Project).filter(Project.status == 1).count(),
            "total_keywords": 0,
            "keyword_found": 0,
            "company_found": 0,
            "overall_hit_rate": 0
        }

    kw_hits = db.query(IndexCheckRecord).filter(IndexCheckRecord.keyword_found == True).count()
    co_hits = db.query(IndexCheckRecord).filter(IndexCheckRecord.company_found == True).count()

    # 命中率 = (公司命中的次数 / 总检测次数) * 100
    hit_rate = round((co_hits / total_checks) * 100, 2)

    return {
        "total_projects": db.query(Project).filter(Project.status == 1).count(),
        "total_keywords": total_checks,
        "keyword_found": kw_hits,
        "company_found": co_hits,
        "overall_hit_rate": hit_rate
    }


@router.get("/trends", response_model=List[TrendDataPoint])
async def get_trends(days: int = Query(30), db: Session = Depends(get_db)):
    """获取趋势图数据"""
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    # 使用 substr 确保 SQLite 兼容 YYYY-MM-DD 分组
    stats = db.query(
        func.substr(IndexCheckRecord.check_time, 1, 10).label("date_str"),
        func.count(IndexCheckRecord.id).label("total"),
        func.sum(cast(IndexCheckRecord.keyword_found, Integer)).label("kw_found")
    ).filter(IndexCheckRecord.check_time >= start_date) \
        .group_by("date_str") \
        .order_by("date_str").all()

    if not stats:
        return [TrendDataPoint(date=datetime.now().strftime("%Y-%m-%d"), keyword_found_count=0, total_checks=0)]

    return [
        TrendDataPoint(
            date=s.date_str,
            keyword_found_count=int(s.kw_found or 0),
            total_checks=int(s.total or 0)
        ) for s in stats
    ]