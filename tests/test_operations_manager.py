"""
运营操作模块测试
"""
import pytest
from src.modules.operations_manager import OperationsManager, OrderInfo, ReturnRequest
from src.modules.beauty_knowledge import BeautyKnowledgeBase


class TestOperationsManager:
    """运营操作管理器测试"""

    @pytest.fixture
    def manager(self):
        kb = BeautyKnowledgeBase()
        return OperationsManager(beauty_kb=kb)

    def test_initialization(self, manager):
        """测试初始化"""
        assert manager.beauty_kb is not None
        assert manager.orders == {}

    def test_create_order(self, manager):
        """测试创建订单"""
        items = [{"product_id": "prod_001", "price": 850.0, "quantity": 1}]
        address = {"name": "张三", "phone": "13800138000", "detail": "北京市朝阳区"}
        order = manager.create_order("user_001", items, address)

        assert order.order_id.startswith("ORD")
        assert order.status == "pending"
        assert order.total_amount == 850.0

    def test_get_order(self, manager):
        """测试查询订单"""
        items = [{"product_id": "prod_001", "price": 850.0, "quantity": 1}]
        address = {"name": "张三", "phone": "13800138000", "detail": "北京市朝阳区"}
        order = manager.create_order("user_001", items, address)

        found = manager.get_order(order.order_id)
        assert found is not None
        assert found.order_id == order.order_id

    def test_pay_order(self, manager):
        """测试支付订单"""
        items = [{"product_id": "prod_001", "price": 850.0, "quantity": 1}]
        address = {"name": "张三", "phone": "13800138000", "detail": "北京市朝阳区"}
        order = manager.create_order("user_001", items, address)

        result = manager.pay_order(order.order_id)
        assert result["status"] == "paid"

    def test_ship_order(self, manager):
        """测试发货"""
        items = [{"product_id": "prod_001", "price": 850.0, "quantity": 1}]
        address = {"name": "张三", "phone": "13800138000", "detail": "北京市朝阳区"}
        order = manager.create_order("user_001", items, address)
        manager.pay_order(order.order_id)

        result = manager.ship_order(order.order_id, "SF1234567890", "顺丰速运")
        assert result["status"] == "shipped"
        assert result["tracking_number"] == "SF1234567890"

    def test_confirm_receipt(self, manager):
        """测试确认收货"""
        items = [{"product_id": "prod_001", "price": 850.0, "quantity": 1}]
        address = {"name": "张三", "phone": "13800138000", "detail": "北京市朝阳区"}
        order = manager.create_order("user_001", items, address)
        manager.pay_order(order.order_id)
        manager.ship_order(order.order_id, "SF1234567890", "顺丰速运")

        result = manager.confirm_receipt(order.order_id)
        assert result["status"] == "completed"

    def test_cancel_order(self, manager):
        """测试取消订单"""
        items = [{"product_id": "prod_001", "price": 850.0, "quantity": 1}]
        address = {"name": "张三", "phone": "13800138000", "detail": "北京市朝阳区"}
        order = manager.create_order("user_001", items, address)

        result = manager.cancel_order(order.order_id, "不想要了")
        assert result["status"] == "cancelled"

    def test_track_logistics(self, manager):
        """测试物流追踪"""
        result = manager.track_logistics("SF1234567890")
        assert result["tracking_number"] == "SF1234567890"
        assert "history" in result

    def test_create_return_request(self, manager):
        """测试创建退货申请"""
        items = [{"product_id": "prod_001", "price": 850.0, "quantity": 1}]
        address = {"name": "张三", "phone": "13800138000", "detail": "北京市朝阳区"}
        order = manager.create_order("user_001", items, address)
        manager.pay_order(order.order_id)
        manager.ship_order(order.order_id, "SF1234567890", "顺丰速运")
        manager.confirm_receipt(order.order_id)

        return_req = manager.create_return_request(
            order.order_id, "user_001", "商品有问题", items
        )
        assert return_req.return_id.startswith("RET")
        assert return_req.status == "pending"

    def test_approve_return(self, manager):
        """测试审核通过退货"""
        items = [{"product_id": "prod_001", "price": 850.0, "quantity": 1}]
        address = {"name": "张三", "phone": "13800138000", "detail": "北京市朝阳区"}
        order = manager.create_order("user_001", items, address)
        manager.pay_order(order.order_id)
        manager.ship_order(order.order_id, "SF1234567890", "顺丰速运")
        manager.confirm_receipt(order.order_id)
        return_req = manager.create_return_request(order.order_id, "user_001", "商品有问题", items)

        result = manager.approve_return(return_req.return_id)
        assert result["status"] == "approved"

    def test_check_stock(self, manager):
        """测试库存查询"""
        result = manager.check_stock("prod_001")
        assert result["in_stock"] is True
        assert result["stock"] > 0

    def test_check_price_protection(self, manager):
        """测试价格保护"""
        items = [{"product_id": "prod_001", "price": 850.0, "quantity": 1}]
        address = {"name": "张三", "phone": "13800138000", "detail": "北京市朝阳区"}
        order = manager.create_order("user_001", items, address)

        result = manager.check_price_protection(order.order_id)
        assert "has_price_drop" in result

    def test_get_order_stats(self, manager):
        """测试订单统计"""
        items = [{"product_id": "prod_001", "price": 850.0, "quantity": 1}]
        address = {"name": "张三", "phone": "13800138000", "detail": "北京市朝阳区"}
        manager.create_order("user_001", items, address)

        stats = manager.get_order_stats("user_001")
        assert stats["total_orders"] == 1
        assert stats["pending"] == 1
