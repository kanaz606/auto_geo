# -*- coding: utf-8 -*-
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.index_check_service import IndexCheckService
from backend.database.models import IndexCheckRecord, Keyword
from backend.schemas import ApiResponse

router = APIRouter(prefix="/api/index-check", tags=["收录检测"])

class CheckRequest(BaseModel):
    keyword_id: int
    company_name: str
    platforms: Optional[List[str]] = ["doubao", "qianwen", "deepseek"]

class RecordResponse(BaseModel):
    id: int
    keyword_id: int
    platform: str
    question: str
    answer: Optional[str] = None
    keyword_found: Optional[bool] = False
    company_found: Optional[bool] = False
    check_time: datetime
    model_config = ConfigDict(from_attributes=True)

@router.post("/check", response_model=ApiResponse)
async def check_index(request: CheckRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    keyword = db.query(Keyword).filter(Keyword.id == request.keyword_id).first()
    if not keyword:
        raise HTTPException(status_code=404, detail="关键词不存在")
    service = IndexCheckService(db)
    background_tasks.add_task(
        service.run_ai_search_check,
        keyword_id=request.keyword_id,
        company_name=request.company_name,
        platforms=request.platforms
    )
    return ApiResponse(success=True, message="监测任务已下发至后台执行")

@router.get("/records", response_model=List[RecordResponse])
async def get_records(keyword_id: Optional[int] = Query(None), limit: int = Query(50), db: Session = Depends(get_db)):
    service = IndexCheckService(db)
    return service.get_check_records(keyword_id=keyword_id, limit=limit)