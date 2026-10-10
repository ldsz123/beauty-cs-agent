"""
业务数据看板模块
GMV统计、转化率、客户满意度、问题分类统计、运营报表
"""
import time
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from loguru import logger


class MetricsDashboard:
    """业务数据看板"""

    def __init__(self):
        self.daily_metrics: dict = {}  # date_str -> metrics
        self.issue_stats: dict = defaultdict(lambda: defaultdict(int))
        self.session_metrics: list = []
        logger.info("MetricsDashboard initialized")

    # ========== 数据记录 ==========
    def record_session(self, session_data: dict):
        """记录会话数据"""
        self.session_metrics.append({
            "timestamp": time.time(),
            "session_id": session_data.get("session_id"),
            "intent": session_data.get("intent"),
            "emotion": session_data.get("emotion"),
            "resolved": session_data.get("resolved", False),
            "need_human": session_data.get("need_human", False),
            "processing_time_ms": session_data.get("processing_time_ms", 0),
            "channel": session_data.get("channel", "web"),
        })

    def record_order(self, order_data: dict):
        """记录订单数据"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        if date_str not in self.daily_metrics:
            self.daily_metrics[date_str] = self._empty_metrics()

        metrics = self.daily_metrics[date_str]
        metrics["total_gmv"] += order_data.get("amount", 0)
        metrics["order_count"] += 1
        metrics["avg_order_value"] = metrics["total_gmv"] / metrics["order_count"]

    def record_issue(self, category: str, subcategory: str = None, resolved: bool = True, ai_resolved: bool = True):
        """记录问题统计"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        key = f"{category}/{subcategory}" if subcategory else category

        self.issue_stats[date_str][key] += 1
        if resolved:
            self.issue_stats[date_str][f"{key}_resolved"] += 1
        if ai_resolved:
            self.issue_stats[date_str][f"{key}_ai"] += 1

    def _empty_metrics(self) -> dict:
        """空指标模板"""
        return {
            "total_gmv": 0.0,
            "order_count": 0,
            "avg_order_value": 0.0,
            "uv": 0,
            "pv": 0,
            "consultation_count": 0,
            "conversion_rate": 0.0,
            "ai_session_count": 0,
            "ai_resolved_count": 0,
            "ai_resolution_rate": 0.0,
            "human_escalation_count": 0,
            "human_escalation_rate": 0.0,
            "satisfaction_score": 0.0,
            "feedback_count": 0,
        }

    # ========== 报表查询 ==========
    def get_daily_report(self, date_str: str = None) -> dict:
        """获取日报表"""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        metrics = self.daily_metrics.get(date_str, self._empty_metrics())
        issues = dict(self.issue_stats.get(date_str, {}))

        return {
            "date": date_str,
            "gmv": {
                "total": metrics["total_gmv"],
                "order_count": metrics["order_count"],
                "avg_order_value": metrics["avg_order_value"],
            },
            "conversion": {
                "uv": metrics["uv"],
                "pv": metrics["pv"],
                "consultation_count": metrics["consultation_count"],
                "conversion_rate": metrics["conversion_rate"],
            },
            "ai_service": {
                "session_count": metrics["ai_session_count"],
                "resolved_count": metrics["ai_resolved_count"],
                "resolution_rate": metrics["ai_resolution_rate"],
                "human_escalation_count": metrics["human_escalation_count"],
                "human_escalation_rate": metrics["human_escalation_rate"],
            },
            "satisfaction": {
                "score": metrics["satisfaction_score"],
                "feedback_count": metrics["feedback_count"],
            },
            "issues": issues,
        }

    def get_period_report(self, days: int = 7) -> dict:
        """获取周期报表"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days - 1)  # 包含今天

        total_gmv = 0.0
        total_orders = 0
        total_sessions = 0
        total_resolved = 0
        total_escalations = 0
        issue_summary = defaultdict(int)

        for i in range(days):
            date = start_date + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")

            metrics = self.daily_metrics.get(date_str, {})
            total_gmv += metrics.get("total_gmv", 0)
            total_orders += metrics.get("order_count", 0)
            total_sessions += metrics.get("ai_session_count", 0)
            total_resolved += metrics.get("ai_resolved_count", 0)
            total_escalations += metrics.get("human_escalation_count", 0)

            for key, count in self.issue_stats.get(date_str, {}).items():
                if not key.endswith("_resolved") and not key.endswith("_ai"):
                    issue_summary[key] += count

        return {
            "period": f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}",
            "days": days,
            "gmv": {
                "total": total_gmv,
                "order_count": total_orders,
                "avg_order_value": total_gmv / total_orders if total_orders > 0 else 0,
            },
            "ai_service": {
                "total_sessions": total_sessions,
                "resolved_count": total_resolved,
                "resolution_rate": total_resolved / total_sessions if total_sessions > 0 else 0,
                "escalation_count": total_escalations,
                "escalation_rate": total_escalations / total_sessions if total_sessions > 0 else 0,
            },
            "top_issues": sorted(issue_summary.items(), key=lambda x: x[1], reverse=True)[:10],
        }

    def get_realtime_stats(self) -> dict:
        """获取实时统计"""
        today = datetime.now().strftime("%Y-%m-%d")
        metrics = self.daily_metrics.get(today, self._empty_metrics())

        # 计算今日会话数
        today_sessions = len([s for s in self.session_metrics if datetime.fromtimestamp(s["timestamp"]).strftime("%Y-%m-%d") == today])

        return {
            "today": today,
            "gmv": metrics["total_gmv"],
            "orders": metrics["order_count"],
            "ai_sessions": today_sessions,
            "ai_resolution_rate": metrics["ai_resolution_rate"],
            "active_sessions": len([s for s in self.session_metrics if time.time() - s["timestamp"] < 300]),  # 5分钟内活跃
        }

    def get_issue_distribution(self, days: int = 7) -> list:
        """获取问题分布"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days - 1)  # 包含今天

        issue_counts = defaultdict(int)
        for i in range(days):
            date = start_date + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            for key, count in self.issue_stats.get(date_str, {}).items():
                if not key.endswith("_resolved") and not key.endswith("_ai"):
                    issue_counts[key] += count

        total = sum(issue_counts.values())
        distribution = []
        for key, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
            distribution.append({
                "category": key,
                "count": count,
                "percentage": count / total * 100 if total > 0 else 0,
            })

        return distribution
