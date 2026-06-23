"""市场服务 - 评分系统"""
from __future__ import annotations


def validate_score(score: int) -> bool:
    return 1 <= score <= 5


def format_rating_response(rating: dict) -> dict:
    return {"id":rating.get("id",0),"agent_id":rating.get("agent_id",""),"score":rating.get("score",0),"comment":rating.get("comment",""),"created_at":rating.get("created_at","")}


def compute_average_rating(ratings: list[dict]) -> float:
    if not ratings:
        return 0.0
    scores = [r.get("score",0) for r in ratings]
    return round(sum(scores)/len(scores), 1)