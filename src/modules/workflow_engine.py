"""
工作流引擎
可视化流程编排、条件分支、多轮对话状态机
"""
import time
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger


class NodeType(str, Enum):
    """节点类型"""
    START = "start"
    INTENT = "intent"           # 意图识别
    CONDITION = "condition"     # 条件分支
    ACTION = "action"           # 执行动作
    LLM = "llm"                 # LLM 回复
    HUMAN = "human"             # 转人工
    END = "end"                 # 结束


@dataclass
class WorkflowNode:
    """工作流节点"""
    id: str
    type: NodeType
    name: str
    config: dict = field(default_factory=dict)
    next_nodes: list = field(default_factory=list)  # [(condition, node_id)]


@dataclass
class WorkflowExecution:
    """工作流执行状态"""
    execution_id: str
    workflow_id: str
    current_node_id: str
    variables: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    status: str = "running"  # running/completed/failed


class WorkflowEngine:
    """工作流引擎"""

    def __init__(self):
        self.workflows: dict = {}  # workflow_id -> {nodes: {node_id: WorkflowNode}, start_node: node_id}
        self.executions: dict = {}  # execution_id -> WorkflowExecution
        self.action_handlers: dict = {}  # action_name -> callable
        logger.info("WorkflowEngine initialized")

    def register_workflow(self, workflow_id: str, nodes: list, start_node_id: str):
        """注册工作流"""
        node_map = {}
        for node_data in nodes:
            node = WorkflowNode(
                id=node_data["id"],
                type=NodeType(node_data["type"]),
                name=node_data["name"],
                config=node_data.get("config", {}),
                next_nodes=node_data.get("next_nodes", []),
            )
            node_map[node.id] = node

        self.workflows[workflow_id] = {
            "nodes": node_map,
            "start_node": start_node_id,
        }
        logger.info(f"Workflow registered: {workflow_id} with {len(nodes)} nodes")

    def register_action(self, action_name: str, handler: Callable):
        """注册动作处理器"""
        self.action_handlers[action_name] = handler

    async def start_execution(self, workflow_id: str, variables: dict = None, session_id: str = None) -> WorkflowExecution:
        """启动工作流执行"""
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow not found: {workflow_id}")

        workflow = self.workflows[workflow_id]
        execution_id = f"WF{int(time.time())}"

        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow_id=workflow_id,
            current_node_id=workflow["start_node"],
            variables=variables or {},
        )
        self.executions[execution_id] = execution

        # 开始执行
        await self._execute_node(execution)
        return execution

    async def _execute_node(self, execution: WorkflowExecution):
        """执行当前节点"""
        workflow = self.workflows[execution.workflow_id]
        node = workflow["nodes"][execution.current_node_id]

        execution.history.append({
            "node_id": node.id,
            "node_type": node.type,
            "timestamp": time.time(),
        })

        if node.type == NodeType.END:
            execution.status = "completed"
            return

        if node.type == NodeType.ACTION:
            await self._execute_action(execution, node)
        elif node.type == NodeType.CONDITION:
            await self._evaluate_condition(execution, node)
        elif node.type == NodeType.LLM:
            await self._execute_llm(execution, node)
        elif node.type == NodeType.HUMAN:
            execution.status = "waiting_human"
            return

        # 自动转移到下一节点
        if node.next_nodes and execution.status == "running":
            next_node_id = node.next_nodes[0][1] if isinstance(node.next_nodes[0], tuple) else node.next_nodes[0]
            execution.current_node_id = next_node_id
            await self._execute_node(execution)

    async def _execute_action(self, execution: WorkflowExecution, node: WorkflowNode):
        """执行动作节点"""
        action_name = node.config.get("action")
        if action_name and action_name in self.action_handlers:
            handler = self.action_handlers[action_name]
            result = await handler(execution.variables, node.config)
            execution.variables.update(result or {})

    async def _evaluate_condition(self, execution: WorkflowExecution, node: WorkflowNode):
        """评估条件分支"""
        condition = node.config.get("condition", "")
        # 简单条件评估：检查变量值
        if condition:
            result = self._eval_condition(condition, execution.variables)
            # 根据条件选择下一节点
            for cond, next_node_id in node.next_nodes:
                if cond == str(result).lower():
                    execution.current_node_id = next_node_id
                    await self._execute_node(execution)
                    return

    def _eval_condition(self, condition: str, variables: dict) -> bool:
        """评估条件表达式"""
        # 简单实现：支持 "variable_name == value" 格式
        try:
            if "==" in condition:
                var_name, value = condition.split("==")
                var_name = var_name.strip()
                value = value.strip().strip("'\"")
                return str(variables.get(var_name, "")).lower() == value.lower()
            return False
        except Exception:
            return False

    async def _execute_llm(self, execution: WorkflowExecution, node: WorkflowNode):
        """执行 LLM 节点"""
        prompt_template = node.config.get("prompt", "")
        # 渲染 prompt
        prompt = prompt_template
        for key, value in execution.variables.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))
        execution.variables["last_llm_prompt"] = prompt

    async def resume_execution(self, execution_id: str, user_input: str = None) -> WorkflowExecution:
        """恢复执行（用户输入后）"""
        execution = self.executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution not found: {execution_id}")

        if execution.status == "waiting_human":
            execution.status = "running"
            await self._execute_node(execution)

        return execution

    def get_execution_status(self, execution_id: str) -> Optional[dict]:
        """获取执行状态"""
        execution = self.executions.get(execution_id)
        if not execution:
            return None

        return {
            "execution_id": execution.execution_id,
            "workflow_id": execution.workflow_id,
            "current_node": execution.current_node_id,
            "status": execution.status,
            "variables": execution.variables,
            "history": execution.history,
        }

    def build_default_workflows(self):
        """构建默认工作流"""
        # 售前咨询工作流
        self.register_workflow(
            "presale_consultation",
            [
                {"id": "start", "type": "start", "name": "开始", "next_nodes": [("default", "intent")]},
                {"id": "intent", "type": "intent", "name": "意图识别", "config": {}, "next_nodes": [("product_inquiry", "product_recommend"), ("price_inquiry", "price_info"), ("default", "general_chat")]},
                {"id": "product_recommend", "type": "action", "name": "产品推荐", "config": {"action": "recommend_products"}, "next_nodes": [("default", "llm_reply")]},
                {"id": "price_info", "type": "action", "name": "价格信息", "config": {"action": "query_price"}, "next_nodes": [("default", "llm_reply")]},
                {"id": "general_chat", "type": "llm", "name": "通用回复", "config": {"prompt": "用户说：{user_input}"}, "next_nodes": [("default", "end")]},
                {"id": "llm_reply", "type": "llm", "name": "LLM回复", "config": {"prompt": "根据以下信息回复用户：{product_info}"}, "next_nodes": [("default", "end")]},
                {"id": "end", "type": "end", "name": "结束"},
            ],
            "start",
        )

        # 售后处理工作流
        self.register_workflow(
            "aftersale_service",
            [
                {"id": "start", "type": "start", "name": "开始", "next_nodes": [("default", "intent")]},
                {"id": "intent", "type": "intent", "name": "意图识别", "next_nodes": [("return_refund", "return_check"), ("complaint", "complaint_handle"), ("default", "general_reply")]},
                {"id": "return_check", "type": "condition", "name": "退货检查", "config": {"condition": "order_status == completed"}, "next_nodes": [("true", "return_approve"), ("false", "return_reject")]},
                {"id": "return_approve", "type": "action", "name": "同意退货", "config": {"action": "approve_return"}, "next_nodes": [("default", "llm_reply")]},
                {"id": "return_reject", "type": "llm", "name": "拒绝退货", "config": {"prompt": "抱歉，您的订单不符合退货条件"}, "next_nodes": [("default", "end")]},
                {"id": "complaint_handle", "type": "action", "name": "投诉处理", "config": {"action": "handle_complaint"}, "next_nodes": [("default", "llm_reply")]},
                {"id": "general_reply", "type": "llm", "name": "通用回复", "config": {"prompt": "用户说：{user_input}"}, "next_nodes": [("default", "end")]},
                {"id": "llm_reply", "type": "llm", "name": "LLM回复", "config": {"prompt": "根据处理结果回复用户"}, "next_nodes": [("default", "end")]},
                {"id": "end", "type": "end", "name": "结束"},
            ],
            "start",
        )

        logger.info("Default workflows built")
