# -*- coding: utf-8 -*-
"""
数据模型定义 - 工业级完整版
包含基础发布、GEO、监控及知识库所有表结构
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, func, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base

# 表参数：允许扩展现有表
TABLE_ARGS = {"extend_existing": True}


class Account(Base):
    """账号表"""
    __tablename__ = "accounts"
    __table_args__ = TABLE_ARGS

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False, index=True)
    account_name = Column(String(100), nullable=False)
    username = Column(String(100), nullable=True)  # 平台内的用户名
    cookies = Column(Text, nullable=True)
    storage_state = Column(Text, nullable=True)
    user_agent = Column(String(500), nullable=True)
    status = Column(Integer, default=1)
    last_auth_time = Column(DateTime, nullable=True)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 🌟 关联关系：一个账号可以有多个发布记录
    # cascade="all, delete-orphan" 确保在 Python 层面删除账号时，关联对象也被清理
    publish_records = relationship("PublishRecord", back_populates="account", cascade="all, delete-orphan")


class Article(Base):
    """普通文章表 (手动撰写)"""
    __tablename__ = "articles"
    __table_args__ = TABLE_ARGS

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(String(500), nullable=True)
    category = Column(String(100), nullable=True)
    cover_image = Column(String(500), nullable=True)
    status = Column(Integer, default=0)
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    published_at = Column(DateTime, nullable=True)

    # 关联关系
    publish_records = relationship("PublishRecord", back_populates="article", cascade="all, delete-orphan")


class PublishRecord(Base):
    """发布记录表"""
    __tablename__ = "publish_records"
    __table_args__ = TABLE_ARGS

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 🌟 关键：ondelete="CASCADE" 确保数据库层面级联删除
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)

    publish_status = Column(Integer, default=0)
    platform_url = Column(String(500), nullable=True)
    error_msg = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    published_at = Column(DateTime, nullable=True)

    # 关联关系
    article = relationship("Article", back_populates="publish_records")
    account = relationship("Account", back_populates="publish_records")


# ==================== GEO相关表 ====================

class Project(Base):
    """项目表"""
    __tablename__ = "projects"
    __table_args__ = TABLE_ARGS

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    company_name = Column(String(200), nullable=False)
    domain_keyword = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    industry = Column(String(100), nullable=True)
    status = Column(Integer, default=1)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关联关系：项目删除时，级联删除下的关键词
    keywords = relationship("Keyword", back_populates="project", cascade="all, delete-orphan")


class Keyword(Base):
    """关键词表"""
    __tablename__ = "keywords"
    __table_args__ = TABLE_ARGS

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(200), nullable=False)
    difficulty_score = Column(Integer, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=func.now())

    # 关联关系
    project = relationship("Project", back_populates="keywords")
    articles = relationship("GeoArticle", back_populates="keyword", cascade="all, delete-orphan")
    question_variants = relationship("QuestionVariant", back_populates="keyword", cascade="all, delete-orphan")
    index_records = relationship("IndexCheckRecord", back_populates="keyword", cascade="all, delete-orphan")


class QuestionVariant(Base):
    """问题变体表"""
    __tablename__ = "question_variants"
    __table_args__ = TABLE_ARGS

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False)
    question = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())

    # 关联关系
    keyword = relationship("Keyword", back_populates="question_variants")


class IndexCheckRecord(Base):
    """收录检测记录表"""
    __tablename__ = "index_check_records"
    __table_args__ = TABLE_ARGS

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    keyword_found = Column(Boolean, nullable=True)
    company_found = Column(Boolean, nullable=True)
    check_time = Column(DateTime, default=func.now())

    # 关联关系
    keyword = relationship("Keyword", back_populates="index_records")


class GeoArticle(Base):
    """
    GEO文章表 - 核心业务表
    """
    __tablename__ = "geo_articles"
    __table_args__ = TABLE_ARGS

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(Text, nullable=True)
    content = Column(Text, nullable=False)

    # 质检相关
    quality_score = Column(Integer, nullable=True)
    ai_score = Column(Integer, nullable=True)
    readability_score = Column(Integer, nullable=True)
    quality_status = Column(String(20), default="pending")

    # 发布相关
    platform = Column(String(50), nullable=True)
    publish_status = Column(String(20), default="draft")
    publish_time = Column(DateTime, nullable=True)

    # 强壮性与重试
    retry_count = Column(Integer, default=0)
    error_msg = Column(Text, nullable=True)
    publish_logs = Column(Text, nullable=True)
    platform_url = Column(String(500), nullable=True)  # 发布成功后的链接

    # 效果监测
    index_status = Column(String(20), default="uncheck")
    last_check_time = Column(DateTime, nullable=True)
    index_details = Column(Text, nullable=True)

    # 时间戳
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关联关系
    keyword = relationship("Keyword", back_populates="articles")


# ==================== 知识库相关表 ====================

class KnowledgeCategory(Base):
    __tablename__ = "knowledge_categories"
    __table_args__ = TABLE_ARGS
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    industry = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(Integer, default=1)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    items = relationship("Knowledge", back_populates="category", cascade="all, delete-orphan")


class Knowledge(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = TABLE_ARGS
    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("knowledge_categories.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    type = Column(String(50), default="other")
    status = Column(Integer, default=1)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    category = relationship("KnowledgeCategory", back_populates="items")


class ScheduledTask(Base):
    """
    定时任务配置表
    """
    __tablename__ = "scheduled_tasks"
    __table_args__ = TABLE_ARGS

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="任务名称")
    task_key = Column(String(50), unique=True, nullable=False, comment="任务标识符(代码中对应key)")
    cron_expression = Column(String(50), nullable=False, comment="Cron表达式")
    is_active = Column(Boolean, default=True, comment="是否启用")
    description = Column(Text, nullable=True, comment="任务描述")

    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Task {self.name} : {self.cron_expression}>"