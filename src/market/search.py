"""市场服务 - 搜索功能"""
from __future__ import annotations


def build_search_params(q="", category="", agent_type="", tags="", sort="downloads", order="desc", page=1, page_size=20):
    if sort not in ("downloads","rating","created","name"):
        sort = "downloads"
    if order not in ("asc","desc"):
        order = "desc"
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    return {"q":q.strip(),"category":category,"agent_type":agent_type,"tags":tag_list,"sort":sort,"order":order,"page":page,"page_size":page_size}