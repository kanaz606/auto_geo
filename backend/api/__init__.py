# -*- coding: utf-8 -*-
"""
API模块入口
负责把所有API路由注册进来！
"""

from . import account, article, publish, keywords, geo, index_check, reports, notifications, scheduler, knowledge, article_collection

__all__ = ["account", "article", "publish", "keywords", "geo", "index_check", "reports", "notifications", "scheduler", "knowledge", "article_collection"]
