"""
问题排查链路记录器
记录一次问答经过的节点、模型输入输出、检索结果、业务查询
"""
import time
import uuid
from typing import Optional
from dataclasses import dataclass, field
from collections import deque
from loguru import logger


@dataclass
class TraceNode:
    """链路节点"""
    node: str                # emotion / semantic / entity / retrieval / action / response
    duration_ms: int = 0
    input_summary: dict = field(default_factory=dict)
    output_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node": self.node,
            "duration_ms": self.duration_ms,
            "input": self.input_summary,
            "output": self.output_summary,
        }


@dataclass
class ModelCall:
    """模型调用记录"""
    stage: str               # 哪个阶段调用了模型
    prompt: str = ""
    response: str = ""
    duration_ms: int = 0
    success: bool = True

    def to_dict(self, truncate: int = 500) -> dict:
        return {
            "stage": self.stage,
            "prompt": self.prompt[:truncate],
            "response": str(self.response)[:truncate],
            "duration_ms": self.duration_ms,
            "success": self.success,
        }


@dataclass
class RoutingTrace:
    """一次问答的完整链路"""
    trace_id: str
    session_id: str
    user_message: str
    nodes: list = field(default_factory=list)
    model_calls: list = field(default_factory=list)
    retrieval: dict = field(default_factory=dict)
    business_queries: list = field(default_factory=list)
    final_reply: str = ""
    intent: str = ""
    emotion: str = ""
    need_human: bool = False
    resolved: bool = True
    status: str = "resolved"   # resolved / unresolved / escalated
    total_duration_ms: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self, detail: bool = True) -> dict:
        base = {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "user_message": self.user_message,
            "intent": self.intent,
            "emotion": self.emotion,
            "need_human": self.need_human,
            "resolved": self.resolved,
            "status": self.status,
            "total_duration_ms": self.total_duration_ms,
            "created_at": self.created_at,
            "node_count": len(self.nodes),
        }
        if detail:
            base["nodes"] = [n.to_dict() for n in self.nodes]
            base["model_calls"] = [m.to_dict() for m in self.model_calls]
            base["retrieval"] = self.retrieval
            base["business_queries"] = self.business_queries
            base["final_reply"] = self.final_reply
        return base


class TraceRecorder:
    """链路记录器（内存环形缓冲 + 可扩展落库）"""

    def __init__(self, max_traces: int = 1000):
        self.max_traces = max_traces
        self._traces: dict = {}
        self._order: deque = deque(maxlen=max_traces)
        logger.info(f"TraceRecorder initialized (max={max_traces})")

    # ========== 生命周期 ==========
    def start_trace(self, session_id: str, user_message: str) -> str:
        """开始记录"""
        trace_id = f"tr_{uuid.uuid4().hex[:12]}"
        trace = RoutingTrace(
            trace_id=trace_id,
            session_id=session_id,
            user_message=user_message,
        )
        self._traces[trace_id] = trace
        self._order.append(trace_id)  # deque 超过 maxlen 时自动淘汰最旧

        # 同步清理已从 deque 淘汰的记录
        if len(self._traces) > self.max_traces:
            valid = set(self._order)
            for tid in list(self._traces.keys()):
                if tid not in valid:
                    self._traces.pop(tid, None)
        return trace_id

    def record_node(self, trace_id: str, node: str,
                    input_summary: dict = None, output_summary: dict = None,
                    duration_ms: int = 0):
        """记录节点"""
        trace = self._traces.get(trace_id)
        if not trace:
            return
        trace.nodes.append(TraceNode(
            node=node,
            duration_ms=duration_ms,
            input_summary=input_summary or {},
            output_summary=output_summary or {},
        ))

    def record_model_call(self, trace_id: str, stage: str,
                          prompt: str = "", response: str = "",
                          duration_ms: int = 0, success: bool = True):
        """记录模型调用"""
        trace = self._traces.get(trace_id)
        if not trace:
            return
        trace.model_calls.append(ModelCall(
            stage=stage,
            prompt=prompt,
            response=response,
            duration_ms=duration_ms,
            success=success,
        ))

    def record_retrieval(self, trace_id: str, retrieval_result):
        """记录检索快照"""
        trace = self._traces.get(trace_id)
        if not trace:
            return
        trace.retrieval = {
            "strategy": retrieval_result.strategy,
            "total_candidates": retrieval_result.total_candidates,
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "category": c.category,
                    "final_score": round(c.final_score, 4),
                    "matched_by": c.matched_by,
                }
                for c in retrieval_result.chunks
            ],
        }

    def record_business_query(self, trace_id: str, action: str, result: dict):
        """记录业务查询"""
        trace = self._traces.get(trace_id)
        if not trace:
            return
        trace.business_queries.append({
            "action": action,
            "result": result,
        })

    def finish_trace(self, trace_id: str, reply: str, intent: str = "",
                     emotion: str = "", need_human: bool = False,
                     total_duration_ms: int = 0):
        """结束记录"""
        trace = self._traces.get(trace_id)
        if not trace:
            return
        trace.final_reply = reply
        trace.intent = intent
        trace.emotion = emotion
        trace.need_human = need_human
        trace.resolved = not need_human
        trace.status = "escalated" if need_human else "resolved"
        trace.total_duration_ms = total_duration_ms

    # ========== 查询 ==========
    def get_trace(self, trace_id: str) -> Optional[dict]:
        """获取单条链路详情"""
        trace = self._traces.get(trace_id)
        return trace.to_dict(detail=True) if trace else None

    def list_traces(self, limit: int = 50, session_id: str = None,
                    status: str = None, intent: str = None) -> list:
        """列出链路"""
        results = []
        for trace_id in reversed(self._order):
            trace = self._traces.get(trace_id)
            if not trace:
                continue
            if session_id and trace.session_id != session_id:
                continue
            if status and trace.status != status:
                continue
            if intent and trace.intent != intent:
                continue
            results.append(trace.to_dict(detail=False))
            if len(results) >= limit:
                break
        return results

    def list_unresolved(self, limit: int = 50) -> list:
        """未解决问题列表（待人工跟进）"""
        return self.list_traces(limit=limit, status="escalated")

    def get_stats(self) -> dict:
        """链路统计"""
        total = len(self._traces)
        escalated = sum(1 for t in self._traces.values() if t.status == "escalated")
        durations = [t.total_duration_ms for t in self._traces.values() if t.total_duration_ms > 0]
        return {
            "total_traces": total,
            "escalated": escalated,
            "resolved": total - escalated,
            "escalation_rate": escalated / total if total > 0 else 0,
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
        }
