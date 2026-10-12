"""
人工客服工作台
客服账号管理、转人工工单、客服接管、会话回复、接待范围
"""
import time
import uuid
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger


# ========== 客服账号 ==========
@dataclass
class AgentAccount:
    """客服账号"""
    agent_id: str
    name: str
    status: str = "offline"          # online / offline / busy
    role: str = "agent"              # agent / supervisor / admin
    reception_scope: dict = field(default_factory=dict)
    # reception_scope 示例：{"categories": ["护肤","彩妆"], "channels": ["web","feishu"], "stores": ["旗舰店"]}
    max_concurrent: int = 5
    active_tickets: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    total_handled: int = 0
    avg_handling_time: float = 0.0

    def can_receive(self, category: str = None, channel: str = None) -> bool:
        """判断是否可接待"""
        if self.status != "online":
            return False
        if len(self.active_tickets) >= self.max_concurrent:
            return False
        scope = self.reception_scope
        if scope.get("categories") and category and category not in scope["categories"]:
            return False
        if scope.get("channels") and channel and channel not in scope["channels"]:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "role": self.role,
            "reception_scope": self.reception_scope,
            "max_concurrent": self.max_concurrent,
            "active_count": len(self.active_tickets),
            "total_handled": self.total_handled,
            "avg_handling_time": round(self.avg_handling_time, 1),
        }


# ========== 转人工工单 ==========
@dataclass
class EscalationTicket:
    """转人工工单"""
    ticket_id: str
    session_id: str
    reason: str
    priority: str = "normal"          # low / normal / high / urgent
    category: str = ""
    channel: str = "web"
    user_message: str = ""
    emotion: str = ""
    status: str = "pending"           # pending / assigned / serving / closed
    assigned_agent: Optional[str] = None
    messages: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    assigned_at: Optional[float] = None
    closed_at: Optional[float] = None
    resolution: str = ""

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "session_id": self.session_id,
            "reason": self.reason,
            "priority": self.priority,
            "category": self.category,
            "channel": self.channel,
            "user_message": self.user_message[:200],
            "emotion": self.emotion,
            "status": self.status,
            "assigned_agent": self.assigned_agent,
            "message_count": len(self.messages),
            "created_at": self.created_at,
            "assigned_at": self.assigned_at,
            "closed_at": self.closed_at,
            "resolution": self.resolution,
        }


class HumanServiceManager:
    """人工客服管理器"""

    # 优先级权重（用于队列排序）
    PRIORITY_WEIGHT = {"urgent": 4, "high": 3, "normal": 2, "low": 1}

    def __init__(self):
        self.agents: dict = {}       # agent_id -> AgentAccount
        self.tickets: dict = {}      # ticket_id -> EscalationTicket
        self._create_default_agents()
        logger.info("HumanServiceManager initialized")

    def _create_default_agents(self):
        """创建默认客服账号（演示用）"""
        defaults = [
            {"agent_id": "agent_001", "name": "小美", "role": "agent",
             "reception_scope": {"categories": ["护肤", "彩妆"]}, "max_concurrent": 5},
            {"agent_id": "agent_002", "name": "小丽", "role": "agent",
             "reception_scope": {"categories": ["护肤"]}, "max_concurrent": 3},
            {"agent_id": "agent_003", "name": "主管-王经理", "role": "supervisor",
             "reception_scope": {}, "max_concurrent": 10},
        ]
        for d in defaults:
            self.agents[d["agent_id"]] = AgentAccount(**d)

    # ========== 客服账号管理 ==========
    def create_agent(self, name: str, role: str = "agent",
                     reception_scope: dict = None, max_concurrent: int = 5) -> AgentAccount:
        """创建客服账号"""
        agent_id = f"agent_{uuid.uuid4().hex[:6]}"
        agent = AgentAccount(
            agent_id=agent_id,
            name=name,
            role=role,
            reception_scope=reception_scope or {},
            max_concurrent=max_concurrent,
        )
        self.agents[agent_id] = agent
        logger.info(f"Agent created: {agent_id} ({name})")
        return agent

    def get_agent(self, agent_id: str) -> Optional[AgentAccount]:
        return self.agents.get(agent_id)

    def list_agents(self, status: str = None) -> list:
        """列出客服"""
        agents = list(self.agents.values())
        if status:
            agents = [a for a in agents if a.status == status]
        return [a.to_dict() for a in agents]

    def set_agent_status(self, agent_id: str, status: str) -> dict:
        """设置客服在线状态"""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": "客服不存在"}
        if status not in ("online", "offline", "busy"):
            return {"error": "无效状态"}
        agent.status = status
        logger.info(f"Agent {agent_id} status -> {status}")
        return agent.to_dict()

    def update_reception_scope(self, agent_id: str, scope: dict) -> dict:
        """更新接待范围"""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": "客服不存在"}
        agent.reception_scope = scope
        return agent.to_dict()

    # ========== 转人工工单 ==========
    def create_ticket(self, session_id: str, reason: str, category: str = "",
                      channel: str = "web", user_message: str = "",
                      emotion: str = "", priority: str = None) -> EscalationTicket:
        """创建转人工工单"""
        if priority is None:
            priority = self._infer_priority(emotion, reason)

        ticket_id = f"tk_{uuid.uuid4().hex[:8]}"
        ticket = EscalationTicket(
            ticket_id=ticket_id,
            session_id=session_id,
            reason=reason,
            priority=priority,
            category=category,
            channel=channel,
            user_message=user_message,
            emotion=emotion,
        )
        self.tickets[ticket_id] = ticket
        logger.info(f"Ticket created: {ticket_id} (priority={priority})")

        # 尝试自动分配
        self.auto_assign(ticket_id)
        return ticket

    def _infer_priority(self, emotion: str, reason: str) -> str:
        """根据情感和原因推断优先级"""
        if emotion == "angry":
            return "urgent"
        if emotion in ("anxious", "urgent"):
            return "high"
        if "投诉" in reason or "complaint" in reason:
            return "high"
        return "normal"

    def get_ticket(self, ticket_id: str) -> Optional[EscalationTicket]:
        return self.tickets.get(ticket_id)

    def list_tickets(self, status: str = None, agent_id: str = None,
                     priority: str = None) -> list:
        """列出工单（按优先级和创建时间排序）"""
        tickets = list(self.tickets.values())
        if status:
            tickets = [t for t in tickets if t.status == status]
        if agent_id:
            tickets = [t for t in tickets if t.assigned_agent == agent_id]
        if priority:
            tickets = [t for t in tickets if t.priority == priority]

        tickets.sort(
            key=lambda t: (self.PRIORITY_WEIGHT.get(t.priority, 0), t.created_at),
            reverse=True,
        )
        return [t.to_dict() for t in tickets]

    def get_queue(self) -> list:
        """待分配队列"""
        return self.list_tickets(status="pending")

    # ========== 分配 ==========
    def auto_assign(self, ticket_id: str) -> dict:
        """自动分配：选择可接待且负载最低的在线客服"""
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return {"error": "工单不存在"}

        candidates = [
            a for a in self.agents.values()
            if a.can_receive(ticket.category, ticket.channel)
        ]
        if not candidates:
            logger.info(f"No available agent for ticket {ticket_id}, staying in queue")
            return {"status": "queued", "ticket_id": ticket_id}

        # 选负载最低的
        candidates.sort(key=lambda a: len(a.active_tickets))
        agent = candidates[0]
        return self.assign_to_agent(ticket_id, agent.agent_id)

    def assign_to_agent(self, ticket_id: str, agent_id: str) -> dict:
        """手动分配工单"""
        ticket = self.tickets.get(ticket_id)
        agent = self.agents.get(agent_id)
        if not ticket:
            return {"error": "工单不存在"}
        if not agent:
            return {"error": "客服不存在"}
        if agent.status != "online":
            return {"error": "客服不在线"}

        ticket.assigned_agent = agent_id
        ticket.status = "assigned"
        ticket.assigned_at = time.time()
        if ticket_id not in agent.active_tickets:
            agent.active_tickets.append(ticket_id)
        logger.info(f"Ticket {ticket_id} assigned to {agent_id}")
        return ticket.to_dict()

    # ========== 客服接管 ==========
    def takeover(self, agent_id: str, session_id: str) -> dict:
        """客服接管会话"""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": "客服不存在"}
        if agent.status != "online":
            return {"error": "客服不在线"}

        # 查找该会话的工单
        ticket = next(
            (t for t in self.tickets.values() if t.session_id == session_id
             and t.status in ("pending", "assigned")),
            None,
        )
        if not ticket:
            # 没有工单则直接创建并接管
            ticket = self.create_ticket(
                session_id, reason="客服主动接管", channel="web"
            )

        ticket.assigned_agent = agent_id
        ticket.status = "serving"
        ticket.assigned_at = ticket.assigned_at or time.time()
        if ticket.ticket_id not in agent.active_tickets:
            agent.active_tickets.append(ticket.ticket_id)

        logger.info(f"Agent {agent_id} took over session {session_id}")
        return ticket.to_dict()

    def agent_reply(self, agent_id: str, session_id: str, content: str) -> dict:
        """客服回复会话"""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": "客服不存在"}

        ticket = next(
            (t for t in self.tickets.values() if t.session_id == session_id
             and t.status == "serving"),
            None,
        )
        if not ticket:
            return {"error": "会话未被接管，无法回复"}

        ticket.messages.append({
            "role": "agent",
            "agent_id": agent_id,
            "agent_name": agent.name,
            "content": content,
            "timestamp": time.time(),
        })
        return {"status": "sent", "ticket_id": ticket.ticket_id, "content": content}

    def close_ticket(self, ticket_id: str, resolution: str = "") -> dict:
        """关闭工单"""
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return {"error": "工单不存在"}

        ticket.status = "closed"
        ticket.closed_at = time.time()
        ticket.resolution = resolution

        # 释放客服
        if ticket.assigned_agent:
            agent = self.agents.get(ticket.assigned_agent)
            if agent and ticket_id in agent.active_tickets:
                agent.active_tickets.remove(ticket_id)
                agent.total_handled += 1
                if ticket.assigned_at:
                    handling_time = time.time() - ticket.assigned_at
                    # 增量平均
                    n = agent.total_handled
                    agent.avg_handling_time = (
                        (agent.avg_handling_time * (n - 1) + handling_time) / n
                    )
        logger.info(f"Ticket {ticket_id} closed")
        return ticket.to_dict()

    def get_agent_workload(self, agent_id: str) -> dict:
        """客服工作负载"""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": "客服不存在"}
        return {
            "agent_id": agent_id,
            "name": agent.name,
            "status": agent.status,
            "active_count": len(agent.active_tickets),
            "max_concurrent": agent.max_concurrent,
            "utilization": len(agent.active_tickets) / agent.max_concurrent if agent.max_concurrent else 0,
            "total_handled": agent.total_handled,
            "avg_handling_time": round(agent.avg_handling_time, 1),
        }

    def get_stats(self) -> dict:
        """人工客服统计"""
        total = len(self.tickets)
        pending = sum(1 for t in self.tickets.values() if t.status == "pending")
        serving = sum(1 for t in self.tickets.values() if t.status == "serving")
        closed = sum(1 for t in self.tickets.values() if t.status == "closed")
        online = sum(1 for a in self.agents.values() if a.status == "online")
        return {
            "total_tickets": total,
            "pending": pending,
            "serving": serving,
            "closed": closed,
            "online_agents": online,
            "total_agents": len(self.agents),
        }
