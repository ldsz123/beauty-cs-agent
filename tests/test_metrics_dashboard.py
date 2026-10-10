"""
业务数据看板模块测试
"""
import pytest
from datetime import datetime, timedelta
from src.modules.metrics_dashboard import MetricsDashboard


class TestMetricsDashboard:
    """业务数据看板测试"""

    @pytest.fixture
    def dashboard(self):
        return MetricsDashboard()

    def test_initialization(self, dashboard):
        """测试初始化"""
        assert dashboard.daily_metrics == {}

    def test_record_session(self, dashboard):
        """测试记录会话"""
        dashboard.record_session({
            "session_id": "test_001",
            "intent": "order_status",
            "emotion": "neutral",
            "resolved": True,
            "need_human": False,
            "processing_time_ms": 1500,
        })
        assert len(dashboard.session_metrics) == 1

    def test_record_order(self, dashboard):
        """测试记录订单"""
        dashboard.record_order({"amount": 199.0})
        today = datetime.now().strftime("%Y-%m-%d")
        assert dashboard.daily_metrics[today]["total_gmv"] == 199.0
        assert dashboard.daily_metrics[today]["order_count"] == 1

    def test_record_issue(self, dashboard):
        """测试记录问题"""
        dashboard.record_issue("order_status", "查询发货", True, True)
        today = datetime.now().strftime("%Y-%m-%d")
        assert dashboard.issue_stats[today]["order_status/查询发货"] == 1

    def test_get_daily_report(self, dashboard):
        """测试获取日报表"""
        dashboard.record_order({"amount": 199.0})
        dashboard.record_session({
            "session_id": "test_001",
            "intent": "order_status",
            "emotion": "neutral",
            "resolved": True,
            "need_human": False,
            "processing_time_ms": 1500,
        })

        report = dashboard.get_daily_report()
        assert "date" in report
        assert "gmv" in report
        assert "ai_service" in report

    def test_get_period_report(self, dashboard):
        """测试获取周期报表"""
        # 记录今天的数据
        today = datetime.now().strftime("%Y-%m-%d")
        dashboard.daily_metrics[today] = dashboard._empty_metrics()
        dashboard.daily_metrics[today]["total_gmv"] = 597.0
        dashboard.daily_metrics[today]["order_count"] = 3

        report = dashboard.get_period_report(days=7)
        assert "period" in report
        assert "gmv" in report
        assert report["gmv"]["order_count"] == 3

    def test_get_realtime_stats(self, dashboard):
        """测试获取实时统计"""
        stats = dashboard.get_realtime_stats()
        assert "today" in stats
        assert "gmv" in stats
        assert "ai_sessions" in stats

    def test_get_issue_distribution(self, dashboard):
        """测试获取问题分布"""
        # 直接记录到 issue_stats 确保日期匹配
        today = datetime.now().strftime("%Y-%m-%d")
        dashboard.issue_stats[today]["order_status/查询发货"] = 5
        dashboard.issue_stats[today]["return_refund/退货"] = 3
        dashboard.issue_stats[today]["order_status/查询物流"] = 2

        dist = dashboard.get_issue_distribution()
        assert len(dist) > 0
        assert all("category" in d for d in dist)
        assert all("count" in d for d in dist)
