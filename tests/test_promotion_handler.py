"""
大促场景模块测试
"""
import pytest
from src.modules.promotion_handler import PromotionHandler, PromotionContext
from src.modules.beauty_knowledge import BeautyKnowledgeBase


class TestPromotionHandler:
    """大促处理器测试"""

    @pytest.fixture
    def handler(self):
        kb = BeautyKnowledgeBase()
        return PromotionHandler(beauty_kb=kb)

    def test_initialization(self, handler):
        """测试初始化"""
        assert handler.beauty_kb is not None
        assert handler.active_promotions == {}

    def test_is_promotion_active_false(self, handler):
        """测试活动不存在"""
        assert handler.is_promotion_active("nonexistent") is False

    def test_calculate_discount_no_promotion(self, handler):
        """测试无促销时价格不变"""
        result = handler.calculate_discount("prod_001", 1)
        assert result["original_price"] > 0
        assert result["discount_price"] == result["original_price"]
        assert result["discount_amount"] == 0

    def test_calculate_discount_with_full_reduction(self, handler):
        """测试满减计算"""
        import time
        handler.active_promotions["test_promo"] = {
            "type": "full_reduction",
            "start_time": time.time() - 100,
            "end_time": time.time() + 10000,
            "rules": {"threshold": 500, "reduction": 100},
        }
        result = handler.calculate_discount("prod_001", 1, "test_promo")
        assert result["discount_amount"] == 100
        assert len(result["applied_rules"]) > 0

    def test_calculate_discount_with_flash_sale(self, handler):
        """测试秒杀价计算"""
        import time
        handler.active_promotions["flash_promo"] = {
            "type": "flash_sale",
            "start_time": time.time() - 100,
            "end_time": time.time() + 10000,
            "rules": {"flash_price": 500},
        }
        result = handler.calculate_discount("prod_001", 1, "flash_promo")
        assert result["discount_price"] == 500

    def test_create_presale_order(self, handler):
        """测试创建预售订单"""
        result = handler.create_presale_order("user_001", "prod_001", 100.0, "promo_001")
        assert "order_id" in result
        assert result["status"] == "deposit_paid"
        assert result["deposit"] == 100.0

    def test_pay_final(self, handler):
        """测试支付尾款"""
        order = handler.create_presale_order("user_001", "prod_001", 100.0, "promo_001")
        result = handler.pay_final(order["order_id"])
        assert result["status"] == "completed"

    def test_pay_final_invalid_order(self, handler):
        """测试支付不存在的订单"""
        result = handler.pay_final("nonexistent")
        assert "error" in result

    def test_get_promotion_script(self, handler):
        """测试获取大促话术"""
        script = handler.get_promotion_script("预热")
        assert script is not None
        assert len(script) > 0

    def test_check_purchase_limit_no_limit(self, handler):
        """测试无限购"""
        result = handler.check_purchase_limit("user_001", "prod_001", None)
        assert result["can_buy"] is True

    def test_check_stock(self, handler):
        """测试库存检查"""
        result = handler.check_stock("prod_001")
        assert result["in_stock"] is True
        assert result["stock"] > 0

    def test_check_stock_not_found(self, handler):
        """测试不存在的商品库存"""
        result = handler.check_stock("nonexistent")
        assert result["in_stock"] is False
