"""
工作流引擎模块测试
"""
import pytest
import pytest_asyncio
from src.modules.workflow_engine import (
    WorkflowEngine, WorkflowNode, WorkflowExecution, NodeType
)


class TestWorkflowEngine:
    """工作流引擎测试"""

    @pytest.fixture
    def engine(self):
        engine = WorkflowEngine()
        engine.build_default_workflows()
        return engine

    def test_initialization(self, engine):
        """测试初始化"""
        assert "presale_consultation" in engine.workflows
        assert "aftersale_service" in engine.workflows

    def test_register_workflow(self, engine):
        """测试注册工作流"""
        engine.register_workflow(
            "test_workflow",
            [
                {"id": "start", "type": "start", "name": "开始", "next_nodes": [("default", "end")]},
                {"id": "end", "type": "end", "name": "结束"},
            ],
            "start",
        )
        assert "test_workflow" in engine.workflows

    def test_register_action(self, engine):
        """测试注册动作"""
        async def mock_handler(variables, config):
            return {"result": "ok"}
        engine.register_action("test_action", mock_handler)
        assert "test_action" in engine.action_handlers

    @pytest.mark.asyncio
    async def test_start_execution(self, engine):
        """测试启动工作流"""
        execution = await engine.start_execution("presale_consultation", {"user_input": "你好"})
        assert execution.execution_id.startswith("WF")
        assert execution.workflow_id == "presale_consultation"

    @pytest.mark.asyncio
    async def test_execution_status(self, engine):
        """测试获取执行状态"""
        execution = await engine.start_execution("presale_consultation")
        status = engine.get_execution_status(execution.execution_id)
        assert status is not None
        assert status["execution_id"] == execution.execution_id

    @pytest.mark.asyncio
    async def test_resume_execution(self, engine):
        """测试恢复执行"""
        execution = await engine.start_execution("presale_consultation")
        resumed = await engine.resume_execution(execution.execution_id, "用户输入")
        assert resumed.execution_id == execution.execution_id

    def test_default_workflows_built(self, engine):
        """测试默认工作流已构建"""
        presale = engine.workflows["presale_consultation"]
        assert len(presale["nodes"]) == 7

        aftersale = engine.workflows["aftersale_service"]
        assert len(aftersale["nodes"]) == 9
