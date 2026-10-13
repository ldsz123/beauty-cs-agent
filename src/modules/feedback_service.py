"""
用户反馈服务
对回答点赞/点踩 + 评论，关联链路以便回溯与优化
"""
import time
import uuid
from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger


@dataclass
class Feedback:
    """用户反馈"""
    feedback_id: str
    trace_id: str
    session_id: str
    rating: str                  # up / down
    comment: str = ""
    user_message: str = ""
    reply: str = ""
    intent: str = ""
    route: str = ""
    sources: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "rating": self.rating,
            "comment": self.comment,
            "user_message": self.user_message[:200],
            "reply": self.reply[:300],
            "intent": self.intent,
            "route": self.route,
            "source_count": len(self.sources),
            "created_at": self.created_at,
        }


class FeedbackService:
    """用户反馈服务"""

    def __init__(self, max_records: int = 5000):
        self.max_records = max_records
        self.feedbacks: dict = {}
        self._order: list = []
        logger.info("FeedbackService initialized")

    def submit(self, trace_id: str, rating: str, session_id: str = "",
               comment: str = "", user_message: str = "", reply: str = "",
               intent: str = "", route: str = "", sources: list = None) -> Feedback:
        """提交反馈"""
        if rating not in ("up", "down"):
            raise ValueError("rating must be 'up' or 'down'")

        # 同一链路重复提交则覆盖
        existing = next((f for f in self.feedbacks.values() if f.trace_id == trace_id), None)
        if existing:
            existing.rating = rating
            existing.comment = comment or existing.comment
            existing.created_at = time.time()
            logger.info(f"Feedback updated: {trace_id} -> {rating}")
            return existing

        feedback_id = f"fb_{uuid.uuid4().hex[:8]}"
        fb = Feedback(
            feedback_id=feedback_id,
            trace_id=trace_id,
            session_id=session_id,
            rating=rating,
            comment=comment,
            user_message=user_message,
            reply=reply,
            intent=intent,
            route=route,
            sources=sources or [],
        )
        self.feedbacks[feedback_id] = fb
        self._order.append(feedback_id)

        # 淘汰最旧
        if len(self._order) > self.max_records:
            oldest = self._order.pop(0)
            self.feedbacks.pop(oldest, None)

        logger.info(f"Feedback submitted: {trace_id} -> {rating}")
        return fb

    def list(self, limit: int = 50, rating: str = None) -> list:
        """反馈列表（新的在前）"""
        items = [self.feedbacks[fid] for fid in reversed(self._order) if fid in self.feedbacks]
        if rating:
            items = [f for f in items if f.rating == rating]
        return [f.to_dict() for f in items[:limit]]

    def list_negative(self, limit: int = 50) -> list:
        """差评列表（用于优化）"""
        return self.list(limit=limit, rating="down")

    def get_stats(self) -> dict:
        """反馈统计"""
        total = len(self.feedbacks)
        ups = sum(1 for f in self.feedbacks.values() if f.rating == "up")
        downs = total - ups

        # 按意图统计差评
        down_by_intent = defaultdict(int)
        for f in self.feedbacks.values():
            if f.rating == "down" and f.intent:
                down_by_intent[f.intent] += 1

        # 按路由统计
        by_route = defaultdict(lambda: {"up": 0, "down": 0})
        for f in self.feedbacks.values():
            if f.route:
                by_route[f.route][f.rating] += 1

        return {
            "total": total,
            "up": ups,
            "down": downs,
            "satisfaction_rate": round(ups / total * 100, 1) if total else 0.0,
            "down_by_intent": dict(sorted(down_by_intent.items(), key=lambda x: -x[1])),
            "by_route": {k: dict(v) for k, v in by_route.items()},
        }
