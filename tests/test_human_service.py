"""
人工客服工作台测试
"""
import pytest
from src.modules.human_service import HumanServiceManager, AgentAccount, EscalationTicket


class TestHumanServiceManager:
    """人工客服管理器测试"""

    @pytest.fixture
    def manager(self):
        return HumanServiceManager()

    def test_default_agents(self, manager):
        """测试默认客服账号"""
        agents = manager.list_agents()
        assert len(agents) == 3

    def test_create_agent(self, manager):
        """测试创建客服"""
        a = manager.create_agent("测试客服", role="agent",
                                 reception_scope={"categories": ["护肤"]})
        assert a.agent_id.startswith("agent_")
        assert a.name == "测试客服"
        assert len(manager.agents) == 4

    def test_set_agent_status(self, manager):
        """测试设置在线状态"""
        result = manager.set_agent_status("agent_001", "online")
        assert result["status"] == "online"

    def test_set_agent_status_invalid(self, manager):
        """测试无效状态"""
        result = manager.set_agent_status("agent_001", "invalid")
        assert "error" in result

    def test_set_agent_status_not_found(self, manager):
        """测试不存在的客服"""
        result = manager.set_agent_status("nonexistent", "online")
        assert "error" in result

    def test_update_reception_scope(self, manager):
        """测试更新接待范围"""
        result = manager.update_reception_scope(
            "agent_001", {"categories": ["彩妆"], "channels": ["web"]}
        )
        assert result["reception_scope"]["categories"] == ["彩妆"]

    def test_can_receive_scope(self, manager):
        """测试接待范围匹配"""
        agent = manager.get_agent("agent_001")
        agent.status = "online"
        assert agent.can_receive("护肤") is True
        assert agent.can_receive("家电") is False

    def test_can_receive_offline(self, manager):
        """测试离线客服不能接待"""
        agent = manager.get_agent("agent_001")
        agent.status = "offline"
        assert agent.can_receive("护肤") is False

    def test_can_receive_max_concurrent(self, manager):
        """测试超过最大并发不能接待"""
        agent = manager.get_agent("agent_002")
        agent.status = "online"
        agent.active_tickets = ["t1", "t2", "t3"]  # max=3
        assert agent.can_receive("护肤") is False

    def test_create_ticket(self, manager):
        """测试创建工单"""
        ticket = manager.create_ticket(
            session_id="sess_001",
            reason="return_refund",
            category="护肤",
            user_message="我要退货",
            emotion="angry",
        )
        assert ticket.ticket_id.startswith("tk_")
        assert ticket.priority == "urgent"  # angry -> urgent

    def test_priority_inference(self, manager):
        """测试优先级推断"""
        assert manager._infer_priority("angry", "") == "urgent"
        assert manager._infer_priority("anxious", "") == "high"
        assert manager._infer_priority("neutral", "投诉") == "high"
        assert manager._infer_priority("neutral", "") == "normal"

    def test_auto_assign(self, manager):
        """测试自动分配"""
        # 先让客服在线
        manager.set_agent_status("agent_001", "online")
        manager.set_agent_status("agent_002", "online")

        ticket = manager.create_ticket(
            session_id="sess_001", reason="咨询", category="护肤"
        )
        # 应自动分配给负载最低的
        assert ticket.assigned_agent is not None
        assert ticket.status == "assigned"

    def test_auto_assign_no_agent(self, manager):
        """测试无可用客服时排队"""
        # 所有客服离线
        for aid in manager.agents:
            manager.set_agent_status(aid, "offline")

        ticket = manager.create_ticket(session_id="sess_001", reason="咨询")
        assert ticket.status == "pending"
        assert ticket.assigned_agent is None

    def test_assign_to_agent(self, manager):
        """测试手动分配"""
        manager.set_agent_status("agent_001", "online")
        ticket = manager.create_ticket(session_id="sess_001", reason="咨询")
        # 先取消自动分配
        ticket.assigned_agent = None
        ticket.status = "pending"

        result = manager.assign_to_agent(ticket.ticket_id, "agent_001")
        assert result["assigned_agent"] == "agent_001"
        assert result["status"] == "assigned"

    def test_assign_to_offline_agent(self, manager):
        """测试分配给离线客服"""
        ticket = manager.create_ticket(session_id="sess_001", reason="咨询")
        result = manager.assign_to_agent(ticket.ticket_id, "agent_002")  # 离线
        assert "error" in result

    def test_takeover(self, manager):
        """测试客服接管"""
        manager.set_agent_status("agent_001", "online")
        result = manager.takeover("agent_001", "sess_001")
        assert result["assigned_agent"] == "agent_001"
        assert result["status"] == "serving"

    def test_agent_reply(self, manager):
        """测试客服回复"""
        manager.set_agent_status("agent_001", "online")
        manager.takeover("agent_001", "sess_001")

        result = manager.agent_reply("agent_001", "sess_001", "您好，我来帮您处理")
        assert result["status"] == "sent"

        ticket = next(t for t in manager.tickets.values() if t.session_id == "sess_001")
        assert len(ticket.messages) == 1
        assert ticket.messages[0]["role"] == "agent"

    def test_agent_reply_not_taken_over(self, manager):
        """测试未接管时回复失败"""
        result = manager.agent_reply("agent_001", "sess_not_taken", "回复")
        assert "error" in result

    def test_close_ticket(self, manager):
        """测试关闭工单"""
        manager.set_agent_status("agent_001", "online")
        result = manager.takeover("agent_001", "sess_001")
        ticket_id = result["ticket_id"]

        closed = manager.close_ticket(ticket_id, resolution="已解决")
        assert closed["status"] == "closed"
        assert closed["resolution"] == "已解决"

        # 客服负载应释放
        agent = manager.get_agent("agent_001")
        assert ticket_id not in agent.active_tickets
        assert agent.total_handled == 1

    def test_list_tickets_priority_sort(self, manager):
        """测试工单按优先级排序"""
        manager.create_ticket(session_id="s1", reason="咨询", emotion="neutral")  # normal
        manager.create_ticket(session_id="s2", reason="投诉", emotion="angry")     # urgent

        tickets = manager.list_tickets()
        assert tickets[0]["priority"] == "urgent"

    def test_get_queue(self, manager):
        """测试待分配队列"""
        for aid in manager.agents:
            manager.set_agent_status(aid, "offline")
        manager.create_ticket(session_id="s1", reason="咨询")

        queue = manager.get_queue()
        assert len(queue) == 1
        assert queue[0]["status"] == "pending"

    def test_get_stats(self, manager):
        """测试统计"""
        manager.set_agent_status("agent_001", "online")
        manager.create_ticket(session_id="s1", reason="咨询")

        stats = manager.get_stats()
        assert stats["total_tickets"] == 1
        assert stats["online_agents"] == 1

    def test_get_agent_workload(self, manager):
        """测试工作负载"""
        manager.set_agent_status("agent_001", "online")
        manager.takeover("agent_001", "sess_001")

        wl = manager.get_agent_workload("agent_001")
        assert wl["active_count"] == 1
        assert wl["utilization"] == 0.2  # 1/5
