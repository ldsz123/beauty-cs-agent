"""
用户反馈服务测试
"""
import pytest
from src.modules.feedback_service import FeedbackService, Feedback


class TestFeedbackService:
    """用户反馈服务测试"""

    @pytest.fixture
    def svc(self):
        return FeedbackService()

    def test_submit_up(self, svc):
        fb = svc.submit("tr_001", "up", session_id="s1")
        assert fb.feedback_id.startswith("fb_")
        assert fb.rating == "up"

    def test_submit_down(self, svc):
        fb = svc.submit("tr_002", "down", comment="答非所问")
        assert fb.rating == "down"
        assert fb.comment == "答非所问"

    def test_submit_invalid_rating(self, svc):
        with pytest.raises(ValueError):
            svc.submit("tr_003", "maybe")

    def test_submit_with_context(self, svc):
        fb = svc.submit(
            "tr_004", "up", session_id="s1",
            user_message="怎么退货", reply="7天无理由退货",
            intent="return_refund", route="knowledge",
        )
        assert fb.intent == "return_refund"
        assert fb.route == "knowledge"

    def test_duplicate_submit_overwrites(self, svc):
        svc.submit("tr_005", "up")
        svc.submit("tr_005", "down", comment="改主意了")
        assert len(svc.feedbacks) == 1
        fb = list(svc.feedbacks.values())[0]
        assert fb.rating == "down"
        assert fb.comment == "改主意了"

    def test_list(self, svc):
        svc.submit("tr_001", "up")
        svc.submit("tr_002", "down")
        items = svc.list()
        assert len(items) == 2
        # 新的在前
        assert items[0]["trace_id"] == "tr_002"

    def test_list_filter_rating(self, svc):
        svc.submit("tr_001", "up")
        svc.submit("tr_002", "down")
        ups = svc.list(rating="up")
        assert len(ups) == 1
        assert ups[0]["rating"] == "up"

    def test_list_negative(self, svc):
        svc.submit("tr_001", "up")
        svc.submit("tr_002", "down")
        assert len(svc.list_negative()) == 1

    def test_stats(self, svc):
        svc.submit("tr_001", "up")
        svc.submit("tr_002", "up")
        svc.submit("tr_003", "down", intent="shipping_query")
        stats = svc.get_stats()
        assert stats["total"] == 3
        assert stats["up"] == 2
        assert stats["down"] == 1
        assert stats["satisfaction_rate"] == 66.7

    def test_stats_down_by_intent(self, svc):
        svc.submit("tr_001", "down", intent="return_refund")
        svc.submit("tr_002", "down", intent="return_refund")
        svc.submit("tr_003", "down", intent="shipping_query")
        stats = svc.get_stats()
        assert stats["down_by_intent"]["return_refund"] == 2

    def test_stats_empty(self, svc):
        stats = svc.get_stats()
        assert stats["total"] == 0
        assert stats["satisfaction_rate"] == 0.0

    def test_eviction(self):
        svc = FeedbackService(max_records=3)
        for i in range(5):
            svc.submit(f"tr_{i}", "up")
        assert len(svc.feedbacks) == 3
        assert svc.feedbacks.get("fb_" + "0" * 8) is None  # 已被淘汰（不存在即可）

    def test_to_dict(self, svc):
        fb = svc.submit("tr_001", "up", user_message="很长的消息" * 50)
        d = fb.to_dict()
        assert "feedback_id" in d
        assert len(d["user_message"]) <= 200
