"""
问题排查链路记录器测试
"""
import pytest
from src.modules.trace_recorder import TraceRecorder, TraceNode, ModelCall, RoutingTrace


class TestTraceRecorder:
    """链路记录器测试"""

    @pytest.fixture
    def recorder(self):
        return TraceRecorder(max_traces=100)

    def test_start_trace(self, recorder):
        """测试开始记录"""
        trace_id = recorder.start_trace("sess_001", "你好")
        assert trace_id.startswith("tr_")
        trace = recorder.get_trace(trace_id)
        assert trace["session_id"] == "sess_001"
        assert trace["user_message"] == "你好"

    def test_record_node(self, recorder):
        """测试记录节点"""
        trace_id = recorder.start_trace("sess_001", "你好")
        recorder.record_node(
            trace_id, "emotion",
            input_summary={"message": "你好"},
            output_summary={"emotion": "neutral"},
            duration_ms=50,
        )
        trace = recorder.get_trace(trace_id)
        assert trace["node_count"] == 1
        assert trace["nodes"][0]["node"] == "emotion"
        assert trace["nodes"][0]["duration_ms"] == 50

    def test_record_model_call(self, recorder):
        """测试记录模型调用"""
        trace_id = recorder.start_trace("sess_001", "你好")
        recorder.record_model_call(
            trace_id, "semantic",
            prompt="识别意图",
            response='{"intent": "general_chat"}',
            duration_ms=200,
        )
        trace = recorder.get_trace(trace_id)
        assert len(trace["model_calls"]) == 1
        assert trace["model_calls"][0]["stage"] == "semantic"

    def test_record_retrieval(self, recorder):
        """测试记录检索快照"""
        from src.modules.retrieval_engine import RetrievalResult, RetrievedChunk

        trace_id = recorder.start_trace("sess_001", "退货")
        result = RetrievalResult(
            query="退货",
            chunks=[RetrievedChunk(
                chunk_id="kb_001", content="退货政策", category="退货",
                final_score=0.9, matched_by=["keyword", "vector"],
            )],
            total_candidates=5,
            strategy="hybrid",
        )
        recorder.record_retrieval(trace_id, result)
        trace = recorder.get_trace(trace_id)
        assert trace["retrieval"]["strategy"] == "hybrid"
        assert trace["retrieval"]["total_candidates"] == 5
        assert len(trace["retrieval"]["chunks"]) == 1

    def test_record_business_query(self, recorder):
        """测试记录业务查询"""
        trace_id = recorder.start_trace("sess_001", "查订单")
        recorder.record_business_query(trace_id, "query_order", {"status": "success"})
        trace = recorder.get_trace(trace_id)
        assert len(trace["business_queries"]) == 1
        assert trace["business_queries"][0]["action"] == "query_order"

    def test_finish_trace(self, recorder):
        """测试结束记录"""
        trace_id = recorder.start_trace("sess_001", "你好")
        recorder.finish_trace(
            trace_id, reply="您好", intent="general_chat",
            emotion="neutral", need_human=False, total_duration_ms=150,
        )
        trace = recorder.get_trace(trace_id)
        assert trace["final_reply"] == "您好"
        assert trace["status"] == "resolved"
        assert trace["total_duration_ms"] == 150

    def test_finish_trace_escalated(self, recorder):
        """测试转人工的链路"""
        trace_id = recorder.start_trace("sess_001", "投诉")
        recorder.finish_trace(trace_id, reply="转人工", need_human=True)
        trace = recorder.get_trace(trace_id)
        assert trace["status"] == "escalated"
        assert trace["resolved"] is False

    def test_list_traces(self, recorder):
        """测试列出链路"""
        for i in range(5):
            trace_id = recorder.start_trace(f"sess_{i}", f"消息{i}")
            recorder.finish_trace(trace_id, reply=f"回复{i}", intent="general_chat")

        traces = recorder.list_traces(limit=10)
        assert len(traces) == 5
        # 详情模式应包含 nodes
        assert "nodes" not in traces[0]

    def test_list_traces_filter_session(self, recorder):
        """测试按会话过滤"""
        t1 = recorder.start_trace("sess_A", "消息1")
        t2 = recorder.start_trace("sess_B", "消息2")
        recorder.finish_trace(t1, reply="回复1")
        recorder.finish_trace(t2, reply="回复2")

        traces = recorder.list_traces(session_id="sess_A")
        assert len(traces) == 1
        assert traces[0]["session_id"] == "sess_A"

    def test_list_unresolved(self, recorder):
        """测试未解决问题列表"""
        t1 = recorder.start_trace("sess_A", "投诉")
        recorder.finish_trace(t1, reply="转人工", need_human=True)
        t2 = recorder.start_trace("sess_B", "咨询")
        recorder.finish_trace(t2, reply="回复", need_human=False)

        unresolved = recorder.list_unresolved()
        assert len(unresolved) == 1
        assert unresolved[0]["session_id"] == "sess_A"

    def test_get_stats(self, recorder):
        """测试链路统计"""
        t1 = recorder.start_trace("sess_A", "投诉")
        recorder.finish_trace(t1, reply="转人工", need_human=True, total_duration_ms=100)
        t2 = recorder.start_trace("sess_B", "咨询")
        recorder.finish_trace(t2, reply="回复", need_human=False, total_duration_ms=200)

        stats = recorder.get_stats()
        assert stats["total_traces"] == 2
        assert stats["escalated"] == 1
        assert stats["resolved"] == 1
        assert stats["avg_duration_ms"] == 150

    def test_get_trace_not_found(self, recorder):
        """测试获取不存在的链路"""
        assert recorder.get_trace("nonexistent") is None

    def test_max_traces_eviction(self):
        """测试超出上限淘汰"""
        recorder = TraceRecorder(max_traces=3)
        ids = []
        for i in range(5):
            ids.append(recorder.start_trace(f"sess_{i}", f"消息{i}"))

        # 最早的应被淘汰
        assert recorder.get_trace(ids[0]) is None
        assert recorder.get_trace(ids[-1]) is not None
