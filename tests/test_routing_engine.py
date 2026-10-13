"""
智能路由引擎测试
"""
import pytest
from src.modules.routing_engine import (
    RoutingEngine, RoutingDecision, ROUTE_INTENTS, ALLOWED_ACTIONS
)


class TestSlotExtraction:
    """槽位提取测试"""

    def test_extract_order_ids_prefixed(self):
        ids = RoutingEngine.extract_order_ids("帮我查订单PDD-20240101-ABCD")
        assert ids == ["PDD-20240101-ABCD"]

    def test_extract_order_ids_labeled(self):
        ids = RoutingEngine.extract_order_ids("订单号：TB20240101123456")
        assert len(ids) == 1

    def test_extract_order_ids_none(self):
        assert RoutingEngine.extract_order_ids("你好") == []

    def test_extract_product_sku(self):
        assert RoutingEngine.extract_product_sku("查一下SKU-ABC123") == "SKU-ABC123"

    def test_extract_product_sku_labeled(self):
        assert RoutingEngine.extract_product_sku("商品编号：P001") == "P001"


class TestGuardRules:
    """守卫规则测试"""

    @pytest.fixture
    def engine(self):
        return RoutingEngine(llm_client=None)

    @pytest.mark.asyncio
    async def test_guard_human(self, engine):
        d = await engine.decide("我要转人工")
        assert d.route == "human"
        assert d.decided_by == "rule"

    @pytest.mark.asyncio
    async def test_guard_ambiguous_order(self, engine):
        d = await engine.decide("我有个订单想查一下")
        assert d.route == "clarify"
        assert d.question is not None

    @pytest.mark.asyncio
    async def test_guard_ambiguous_with_order_id(self, engine):
        # 有明确订单号则不澄清
        d = await engine.decide("我有个订单PDD-20240101-ABCD想查一下")
        assert d.route != "clarify"

    @pytest.mark.asyncio
    async def test_guard_merchant_address(self, engine):
        d = await engine.decide("你们的退货地址是什么？")
        assert d.route == "knowledge"

    @pytest.mark.asyncio
    async def test_guard_personal_address_not_knowledge(self, engine):
        # 个人订单地址 → 不是通用地址知识
        d = await engine.decide("我的订单收货地址填错了")
        assert d.route != "knowledge" or "地址" not in (d.knowledge_query or "")


class TestRuleRouting:
    """规则路由测试（无 LLM）"""

    @pytest.fixture
    def engine(self):
        return RoutingEngine(llm_client=None)

    @pytest.mark.asyncio
    async def test_route_order_query(self, engine):
        d = await engine.decide("帮我查订单PDD-20240101-ABCD")
        assert d.route == "business"
        assert d.intent == "order_query"
        assert d.order_id == "PDD-20240101-ABCD"

    @pytest.mark.asyncio
    async def test_route_shipping(self, engine):
        d = await engine.decide("我的快递到哪了")
        assert d.route == "business"
        assert d.intent == "shipping_query"

    @pytest.mark.asyncio
    async def test_route_product_inventory(self, engine):
        d = await engine.decide("这个SKU-ABC123还有库存吗")
        assert d.route == "business"
        assert d.intent == "product_query"
        assert d.product_field == "inventory"

    @pytest.mark.asyncio
    async def test_route_product_price(self, engine):
        d = await engine.decide("SKU-ABC123多少钱")
        assert d.product_field == "price"

    @pytest.mark.asyncio
    async def test_route_knowledge(self, engine):
        d = await engine.decide("退货政策是什么")
        assert d.route == "knowledge"
        assert d.intent == "knowledge"

    @pytest.mark.asyncio
    async def test_route_business_action_cancel(self, engine):
        d = await engine.decide("帮我取消订单PDD-20240101-ABCD")
        assert d.intent == "business_action"
        assert d.action == "cancel_order"

    @pytest.mark.asyncio
    async def test_route_business_action_refund(self, engine):
        d = await engine.decide("我要申请退款PDD-20240101-ABCD")
        assert d.action == "apply_refund"

    @pytest.mark.asyncio
    async def test_route_refund_eligibility_hybrid(self, engine):
        d = await engine.decide("我这个订单能退吗")
        assert d.route == "hybrid"
        assert d.intent == "refund_eligibility"

    @pytest.mark.asyncio
    async def test_route_chitchat(self, engine):
        d = await engine.decide("你好呀")
        assert d.route == "chitchat"

    @pytest.mark.asyncio
    async def test_action_without_order_id_clarify(self, engine):
        d = await engine.decide("帮我取消订单")
        assert d.route == "clarify"
        assert d.question is not None


class TestValidation:
    """一致性校验测试"""

    @pytest.fixture
    def engine(self):
        return RoutingEngine(llm_client=None)

    @pytest.mark.asyncio
    async def test_route_intent_consistency(self, engine):
        """所有决策的 route/intent 必须一致"""
        cases = ["你好", "查订单PDD-20240101-ABCD", "退货政策", "我要转人工",
                 "我有个订单", "快递到哪了", "SKU-ABC123多少钱"]
        for msg in cases:
            d = await engine.decide(msg)
            assert d.validate(), f"{msg} -> route={d.route} intent={d.intent}"

    def test_route_intents_mapping(self):
        """ROUTE_INTENTS 覆盖所有 route"""
        assert set(ROUTE_INTENTS.keys()) == {"business", "knowledge", "hybrid",
                                             "clarify", "human", "chitchat"}

    def test_allowed_actions_allowlist(self):
        """白名单动作"""
        assert ALLOWED_ACTIONS == {"cancel_order", "apply_refund"}


class TestLLMRouting:
    """LLM 路由测试（需显式开启）"""

    @pytest.fixture
    def engine(self, monkeypatch):
        from tests.mocks.llm_mock import MockLLMClient
        monkeypatch.setenv("LLM_ROUTING", "true")
        return RoutingEngine(llm_client=MockLLMClient())

    @pytest.mark.asyncio
    async def test_llm_route(self, engine):
        """开启后由模型给出路由（mock 返回 hybrid/order_query）"""
        d = await engine.decide("随便说点什么")
        assert d.route == "hybrid"
        assert d.intent == "order_query"
        assert d.decided_by == "llm"
        assert d.validate()

    @pytest.mark.asyncio
    async def test_guard_overrides_llm(self, engine):
        """守卫规则优先于 LLM"""
        d = await engine.decide("我要转人工")
        assert d.route == "human"
        assert d.decided_by == "rule"

    def test_llm_routing_disabled_by_default(self, monkeypatch):
        """默认关闭模型路由（走规则，保证低延迟）"""
        from tests.mocks.llm_mock import MockLLMClient
        monkeypatch.delenv("LLM_ROUTING", raising=False)
        engine = RoutingEngine(llm_client=MockLLMClient())
        assert engine.use_llm is False


class TestRoutingStats:
    """路由统计测试"""

    @pytest.fixture
    def engine(self):
        return RoutingEngine(llm_client=None)

    @pytest.mark.asyncio
    async def test_stats(self, engine):
        await engine.decide("你好")
        await engine.decide("查订单PDD-20240101-ABCD")
        stats = engine.get_stats()
        assert stats["total"] == 2
        assert stats["distribution"]["chitchat"] >= 1
        assert stats["distribution"]["business"] >= 1

    def test_route_rules(self):
        rules = RoutingEngine.get_route_rules()
        assert "routes" in rules
        assert "allowed_actions" in rules
        assert "guards" in rules
        assert len(rules["routes"]) == 6
