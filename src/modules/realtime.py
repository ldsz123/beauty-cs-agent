"""
实时通信管理器
基于 WebSocket 的会话实时推送：客服接管、消息互推、工单通知
"""
import time
from typing import Optional
from collections import defaultdict
from loguru import logger


class ConnectionManager:
    """
    连接管理器
    - 会话通道：session_id -> [websocket]
    - 客服通道：agent_id  -> [websocket]
    - 广播通道：所有客服
    """

    def __init__(self):
        self.session_conns: dict = defaultdict(list)   # session_id -> [ws]
        self.agent_conns: dict = defaultdict(list)     # agent_id -> [ws]
        self.agent_broadcast: list = []                # 所有客服连接
        logger.info("ConnectionManager initialized")

    # ========== 连接管理 ==========
    async def connect_session(self, ws, session_id: str):
        await ws.accept()
        self.session_conns[session_id].append(ws)
        logger.info(f"Session connected: {session_id}")

    async def connect_agent(self, ws, agent_id: str):
        await ws.accept()
        self.agent_conns[agent_id].append(ws)
        self.agent_broadcast.append(ws)
        logger.info(f"Agent connected: {agent_id}")

    def disconnect_session(self, ws, session_id: str):
        if ws in self.session_conns.get(session_id, []):
            self.session_conns[session_id].remove(ws)
        if not self.session_conns.get(session_id):
            self.session_conns.pop(session_id, None)

    def disconnect_agent(self, ws, agent_id: str):
        if ws in self.agent_conns.get(agent_id, []):
            self.agent_conns[agent_id].remove(ws)
        if ws in self.agent_broadcast:
            self.agent_broadcast.remove(ws)

    # ========== 推送 ==========
    async def send_to_session(self, session_id: str, message: dict):
        """推送给某会话的所有连接（客户端）"""
        dead = []
        for ws in self.session_conns.get(session_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_session(ws, session_id)

    async def send_to_agent(self, agent_id: str, message: dict):
        """推送给指定客服"""
        dead = []
        for ws in self.agent_conns.get(agent_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_agent(ws, agent_id)

    async def broadcast_to_agents(self, message: dict):
        """广播给所有在线客服"""
        dead = []
        for ws in list(self.agent_broadcast):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.agent_broadcast:
                self.agent_broadcast.remove(ws)

    # ========== 业务事件 ==========
    async def notify_new_ticket(self, ticket: dict):
        """新工单 → 广播给客服"""
        await self.broadcast_to_agents({
            "type": "new_ticket",
            "ticket": ticket,
            "timestamp": time.time(),
        })

    async def notify_takeover(self, session_id: str, agent: dict):
        """客服接管 → 通知客户"""
        await self.send_to_session(session_id, {
            "type": "agent_joined",
            "agent": agent,
            "message": f"客服 {agent.get('name', '')} 已接入，正在为您服务",
            "timestamp": time.time(),
        })

    async def notify_agent_reply(self, session_id: str, agent: dict, content: str):
        """客服回复 → 推送给客户"""
        await self.send_to_session(session_id, {
            "type": "agent_message",
            "agent": agent,
            "content": content,
            "timestamp": time.time(),
        })

    async def notify_ticket_closed(self, session_id: str, resolution: str):
        """工单关闭 → 通知客户"""
        await self.send_to_session(session_id, {
            "type": "ticket_closed",
            "resolution": resolution,
            "timestamp": time.time(),
        })

    def get_stats(self) -> dict:
        """连接统计"""
        return {
            "active_sessions": len(self.session_conns),
            "online_agents": len([k for k, v in self.agent_conns.items() if v]),
            "total_agent_conns": len(self.agent_broadcast),
        }
