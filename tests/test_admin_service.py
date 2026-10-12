"""
运营管理后台测试
"""
import pytest
from src.modules.admin_service import AdminService
from src.modules.beauty_knowledge import BeautyKnowledgeBase
from src.modules.operations_manager import OperationsManager


@pytest.fixture
def admin():
    kb = BeautyKnowledgeBase()
    ops = OperationsManager(beauty_kb=kb)
    return AdminService(beauty_kb=kb, operations_manager=ops)


class TestProductAdmin:
    """商品管理测试"""

    def test_list_products(self, admin):
        result = admin.list_products()
        assert result["total"] > 0

    def test_list_products_pagination(self, admin):
        result = admin.list_products(page=1, page_size=3)
        assert len(result["items"]) <= 3

    def test_list_products_filter_category(self, admin):
        result = admin.list_products(category="护肤")
        assert all(p["category"] == "护肤" for p in result["items"])

    def test_list_products_keyword(self, admin):
        result = admin.list_products(keyword="精华")
        assert result["total"] > 0

    def test_create_product(self, admin):
        p = admin.create_product({"name": "测试面膜", "brand": "TestBrand",
                                  "category": "护肤", "price": 99.0, "stock": 100})
        assert p["id"].startswith("prod_")
        assert admin.get_product(p["id"]) is not None

    def test_update_product(self, admin):
        p = admin.create_product({"name": "测试品", "price": 100.0})
        updated = admin.update_product(p["id"], {"price": 150.0, "name": "改名品"})
        assert updated["price"] == 150.0
        assert updated["name"] == "改名品"

    def test_update_product_not_found(self, admin):
        assert "error" in admin.update_product("nonexistent", {"price": 1})

    def test_delete_product(self, admin):
        p = admin.create_product({"name": "待删品"})
        result = admin.delete_product(p["id"])
        assert result["status"] == "inactive"
        assert admin.get_product(p["id"])["status"] == "inactive"


class TestInventoryAdmin:
    """库存管理测试"""

    def test_list_inventory(self, admin):
        items = admin.list_inventory()
        assert len(items) > 0
        assert "low_stock" in items[0]

    def test_adjust_stock_delta(self, admin):
        pid = "prod_001"
        before = admin.inventory[pid]["stock"]
        result = admin.adjust_stock(pid, delta=10)
        assert result["stock"] == before + 10

    def test_adjust_stock_set(self, admin):
        result = admin.adjust_stock("prod_001", stock=999)
        assert result["stock"] == 999

    def test_adjust_stock_no_negative(self, admin):
        result = admin.adjust_stock("prod_001", delta=-999999)
        assert result["stock"] == 0

    def test_adjust_stock_no_param(self, admin):
        assert "error" in admin.adjust_stock("prod_001")

    def test_low_stock_filter(self, admin):
        admin.adjust_stock("prod_001", stock=10)  # 低于阈值50
        items = admin.list_inventory(low_stock_only=True)
        assert any(i["product_id"] == "prod_001" for i in items)

    def test_set_warning_threshold(self, admin):
        result = admin.set_warning_threshold("prod_001", 100)
        assert result["warning_threshold"] == 100


class TestOrderAdmin:
    """订单管理测试"""

    def test_create_and_list_orders(self, admin):
        admin.create_order("u1", [{"product_id": "prod_001", "price": 100, "quantity": 1}],
                           {"name": "张三"})
        orders = admin.list_orders()
        assert len(orders) == 1

    def test_update_order_status(self, admin):
        o = admin.create_order("u1", [{"price": 100, "quantity": 1}], {})
        result = admin.update_order_status(o["order_id"], "paid")
        assert result["status"] == "paid"

    def test_update_order_not_found(self, admin):
        assert "error" in admin.update_order_status("nonexistent", "paid")


class TestPaymentAdmin:
    """支付管理测试"""

    def test_record_payment(self, admin):
        p = admin.record_payment("ord_001", 199.0, "wechat")
        assert p["payment_id"].startswith("pay_")
        assert p["status"] == "success"

    def test_list_payments(self, admin):
        admin.record_payment("ord_001", 199.0)
        assert len(admin.list_payments()) == 1
        assert len(admin.list_payments(order_id="ord_001")) == 1
        assert len(admin.list_payments(order_id="ord_999")) == 0

    def test_refund_payment(self, admin):
        p = admin.record_payment("ord_001", 199.0)
        result = admin.refund_payment(p["payment_id"])
        assert result["status"] == "refunded"

    def test_refund_payment_not_found(self, admin):
        assert "error" in admin.refund_payment("nonexistent")


class TestShipmentAdmin:
    """物流管理测试"""

    def test_create_shipment(self, admin):
        s = admin.create_shipment("ord_001", "顺丰", "SF123")
        assert s["shipment_id"].startswith("ship_")
        assert s["status"] == "shipped"

    def test_list_shipments(self, admin):
        admin.create_shipment("ord_001", "顺丰", "SF123")
        assert len(admin.list_shipments()) == 1

    def test_update_shipment_status(self, admin):
        s = admin.create_shipment("ord_001", "顺丰", "SF123")
        result = admin.update_shipment_status(s["shipment_id"], "delivered")
        assert result["status"] == "delivered"


class TestRefundAdmin:
    """退款管理测试"""

    def test_refund_flow(self, admin):
        # 创建订单 -> 支付 -> 发货 -> 收货 -> 退货
        o = admin.create_order("u1", [{"product_id": "prod_001", "price": 100, "quantity": 1}], {})
        admin.update_order_status(o["order_id"], "completed")

        # 创建退货申请
        ret = admin.ops.create_return_request(o["order_id"], "u1", "商品问题",
                                              [{"price": 100, "quantity": 1}])
        assert ret is not None

        # 审核通过
        result = admin.approve_refund(ret.return_id)
        assert result["status"] == "approved"
        # 应同步到退款记录
        assert ret.return_id in admin.refunds

    def test_list_refunds(self, admin):
        assert isinstance(admin.list_refunds(), list)


class TestCustomerAdmin:
    """客户管理测试"""

    def test_list_customers(self, admin):
        assert len(admin.list_customers()) == 2

    def test_list_customers_filter_level(self, admin):
        items = admin.list_customers(level="VIP")
        assert all(c["level"] == "VIP" for c in items)

    def test_create_customer(self, admin):
        c = admin.create_customer({"nickname": "新客户", "phone": "137****0000"})
        assert c["customer_id"].startswith("cust_")

    def test_update_customer(self, admin):
        c = admin.create_customer({"nickname": "客户A"})
        result = admin.update_customer(c["customer_id"], {"level": "VIP"})
        assert result["level"] == "VIP"

    def test_delete_customer(self, admin):
        c = admin.create_customer({"nickname": "待删"})
        result = admin.delete_customer(c["customer_id"])
        assert result["status"] == "deleted"
        assert admin.get_customer(c["customer_id"]) is None


class TestUserRoleAdmin:
    """用户与角色管理测试"""

    def test_list_users(self, admin):
        assert len(admin.list_users()) == 3

    def test_create_user(self, admin):
        u = admin.create_user("newuser", "新用户", "role_ops")
        assert u["user_id"].startswith("user_")

    def test_create_duplicate_user(self, admin):
        assert "error" in admin.create_user("admin", "重复", "role_ops")

    def test_update_user(self, admin):
        result = admin.update_user("user_ops01", {"role_id": "role_admin"})
        assert result["role_id"] == "role_admin"

    def test_delete_user(self, admin):
        u = admin.create_user("todelete", "待删", "role_viewer")
        result = admin.delete_user(u["user_id"])
        assert result["status"] == "deleted"

    def test_list_roles(self, admin):
        assert len(admin.list_roles()) == 4

    def test_create_role(self, admin):
        r = admin.create_role("测试角色", ["product:read"])
        assert r["role_id"].startswith("role_")

    def test_delete_role_in_use(self, admin):
        # role_admin 被 user_admin 使用
        assert "error" in admin.delete_role("role_admin")

    def test_delete_unused_role(self, admin):
        r = admin.create_role("临时角色", [])
        assert admin.delete_role(r["role_id"])["status"] == "deleted"

    def test_has_permission_admin(self, admin):
        assert admin.has_permission("user_admin", "anything:write") is True

    def test_has_permission_ops(self, admin):
        assert admin.has_permission("user_ops01", "product:write") is True
        assert admin.has_permission("user_ops01", "user:delete") is False

    def test_has_permission_viewer(self, admin):
        assert admin.has_permission("user_cs01", "order:read") is True
        assert admin.has_permission("user_cs01", "order:write") is False

    def test_has_permission_unknown_user(self, admin):
        assert admin.has_permission("nonexistent", "product:read") is False


class TestConfigAdmin:
    """配置管理测试"""

    def test_list_configs(self, admin):
        assert len(admin.list_configs()) == 4

    def test_get_config(self, admin):
        c = admin.get_config("session_ttl")
        assert c["value"] == 3600

    def test_set_config_update(self, admin):
        result = admin.set_config("session_ttl", 7200)
        assert result["value"] == 7200

    def test_set_config_new(self, admin):
        result = admin.set_config("new_key", "new_value", "新配置")
        assert result["key"] == "new_key"
        assert admin.get_config("new_key")["value"] == "new_value"

    def test_delete_config(self, admin):
        admin.set_config("temp_key", 1)
        result = admin.delete_config("temp_key")
        assert result["status"] == "deleted"
        assert admin.get_config("temp_key") is None


class TestOverview:
    """后台总览测试"""

    def test_get_overview(self, admin):
        overview = admin.get_overview()
        assert "products" in overview
        assert "inventory" in overview
        assert "customers" in overview
        assert "users" in overview
        assert overview["products"]["total"] > 0
