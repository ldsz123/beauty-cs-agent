"""
业务动作执行器测试
"""
import pytest
from src.services.action_executor import BusinessActionExecutor
from src.layers.semantic_layer import IntentType
from src.layers.entity_layer import ExtractedEntities


class TestBusinessActionExecutor:
    """业务动作执行器测试"""

    @pytest.fixture
    def executor(self):
        return BusinessActionExecutor(config={})

    @pytest.mark.asyncio
    async def test_query_order(self, executor):
        """测试订单查询"""
        entities = ExtractedEntities(order_id="TB20240101123456")
        result = await executor.execute(IntentType.ORDER_STATUS, entities)

        assert len(result) > 0
        assert result[0]["action"] == "query_order"
        assert result[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_query_order_no_id(self, executor):
        """测试无订单号查询"""
        entities = ExtractedEntities()
        result = await executor.execute(IntentType.ORDER_STATUS, entities)

        assert len(result) > 0
        assert result[0]["status"] == "need_order_id"

    @pytest.mark.asyncio
    async def test_query_logistics(self, executor):
        """测试物流查询"""
        entities = ExtractedEntities(tracking_number="SF1234567890")
        result = await executor.execute(IntentType.SHIPPING_INQUIRY, entities)

        assert len(result) > 0
        assert result[0]["action"] == "query_logistics"
        assert result[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_initiate_return(self, executor):
        """测试发起退货"""
        entities = ExtractedEntities(order_id="TB20240101123456")
        result = await executor.execute(IntentType.RETURN_REFUND, entities)

        assert len(result) > 0
        assert result[0]["action"] == "initiate_return"
        assert result[0]["status"] == "created"

    @pytest.mark.asyncio
    async def test_handle_complaint(self, executor):
        """测试处理投诉"""
        entities = ExtractedEntities()
        result = await executor.execute(IntentType.COMPLAINT, entities)

        assert len(result) > 0
        assert result[0]["action"] == "handle_complaint"
        assert result[0]["status"] == "recorded"

    @pytest.mark.asyncio
    async def test_query_promotion(self, executor):
        """测试查询促销"""
        entities = ExtractedEntities()
        result = await executor.execute(IntentType.PROMOTION_INQUIRY, entities)

        assert len(result) > 0
        assert result[0]["action"] == "query_promotion"
        assert result[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_unknown_intent(self, executor):
        """测试未知意图"""
        entities = ExtractedEntities()
        result = await executor.execute(IntentType.GENERAL_CHAT, entities)

        assert result == []
