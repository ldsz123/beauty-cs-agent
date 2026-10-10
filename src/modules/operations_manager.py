"""
运营操作模块
订单管理、物流追踪、退货退款执行、库存查询、价格保护
"""
import time
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class OrderInfo:
    """订单信息"""
    order_id: str
    user_id: str
    status: str  # pending/paid/shipped/delivered/completed/returned
    items: list = field(default_factory=list)
    total_amount: float = 0.0
    discount_amount: float = 0.0
    shipping_address: dict = field(default_factory=dict)
    created_at: float = 0.0
    paid_at: Optional[float] = None
    shipped_at: Optional[float] = None
    tracking_number: Optional[str] = None
    express_company: Optional[str] = None


@dataclass
class ReturnRequest:
    """退货退款申请"""
    return_id: str
    order_id: str
    user_id: str
    reason: str
    status: str  # pending/approved/rejected/completed
    items: list = field(default_factory=list)
    refund_amount: float = 0.0
    images: list = field(default_factory=list)
    created_at: float = 0.0


class OperationsManager:
    """运营操作管理器"""

    def __init__(self, beauty_kb=None):
        self.beauty_kb = beauty_kb
        self.orders: dict = {}
        self.returns: dict = {}
        logger.info("OperationsManager initialized")

    # ========== 订单管理 ==========
    def get_order(self, order_id: str) -> Optional[OrderInfo]:
        """查询订单"""
        return self.orders.get(order_id)

    def create_order(self, user_id: str, items: list, address: dict) -> OrderInfo:
        """创建订单"""
        order_id = f"ORD{int(time.time())}{user_id[-4:]}"
        total = sum(item.get("price", 0) * item.get("quantity", 1) for item in items)

        order = OrderInfo(
            order_id=order_id,
            user_id=user_id,
            status="pending",
            items=items,
            total_amount=total,
            shipping_address=address,
            created_at=time.time(),
        )
        self.orders[order_id] = order
        return order

    def pay_order(self, order_id: str) -> dict:
        """支付订单"""
        order = self.orders.get(order_id)
        if not order:
            return {"error": "订单不存在"}
        if order.status != "pending":
            return {"error": "订单状态错误"}

        order.status = "paid"
        order.paid_at = time.time()
        return {"order_id": order_id, "status": "paid"}

    def ship_order(self, order_id: str, tracking_number: str, express_company: str) -> dict:
        """发货"""
        order = self.orders.get(order_id)
        if not order:
            return {"error": "订单不存在"}
        if order.status != "paid":
            return {"error": "订单未支付"}

        order.status = "shipped"
        order.shipped_at = time.time()
        order.tracking_number = tracking_number
        order.express_company = express_company
        return {"order_id": order_id, "status": "shipped", "tracking_number": tracking_number}

    def confirm_receipt(self, order_id: str) -> dict:
        """确认收货"""
        order = self.orders.get(order_id)
        if not order:
            return {"error": "订单不存在"}
        if order.status != "shipped":
            return {"error": "订单未发货"}

        order.status = "completed"
        return {"order_id": order_id, "status": "completed"}

    def cancel_order(self, order_id: str, reason: str = "") -> dict:
        """取消订单"""
        order = self.orders.get(order_id)
        if not order:
            return {"error": "订单不存在"}
        if order.status not in ("pending", "paid"):
            return {"error": "订单状态不允许取消"}

        order.status = "cancelled"
        return {"order_id": order_id, "status": "cancelled", "reason": reason}

    # ========== 物流追踪 ==========
    def track_logistics(self, tracking_number: str) -> dict:
        """物流追踪"""
        # 模拟物流信息
        return {
            "tracking_number": tracking_number,
            "status": "运输中",
            "express_company": "顺丰速运",
            "latest_update": "【上海转运中心】已发出",
            "estimated_delivery": "预计明天送达",
            "history": [
                {"time": "2024-01-15 10:00", "desc": "【上海转运中心】已发出"},
                {"time": "2024-01-15 08:00", "desc": "【上海浦东】已揽收"},
                {"time": "2024-01-15 06:00", "desc": "商家已发货"},
            ],
        }

    # ========== 退货退款 ==========
    def create_return_request(self, order_id: str, user_id: str, reason: str, items: list, images: list = None) -> ReturnRequest:
        """创建退货申请"""
        order = self.orders.get(order_id)
        if not order:
            return None

        return_id = f"RET{int(time.time())}{user_id[-4:]}"
        refund_amount = sum(item.get("price", 0) * item.get("quantity", 1) for item in items)

        return_req = ReturnRequest(
            return_id=return_id,
            order_id=order_id,
            user_id=user_id,
            reason=reason,
            status="pending",
            items=items,
            refund_amount=refund_amount,
            images=images or [],
            created_at=time.time(),
        )
        self.returns[return_id] = return_req
        return return_req

    def approve_return(self, return_id: str) -> dict:
        """审核通过退货"""
        ret = self.returns.get(return_id)
        if not ret:
            return {"error": "退货申请不存在"}

        ret.status = "approved"
        return {"return_id": return_id, "status": "approved"}

    def reject_return(self, return_id: str, reason: str) -> dict:
        """拒绝退货"""
        ret = self.returns.get(return_id)
        if not ret:
            return {"error": "退货申请不存在"}

        ret.status = "rejected"
        return {"return_id": return_id, "status": "rejected", "reason": reason}

    def complete_return(self, return_id: str) -> dict:
        """完成退货退款"""
        ret = self.returns.get(return_id)
        if not ret:
            return {"error": "退货申请不存在"}

        ret.status = "completed"
        # 更新订单状态
        order = self.orders.get(ret.order_id)
        if order:
            order.status = "returned"

        return {"return_id": return_id, "status": "completed", "refund_amount": ret.refund_amount}

    # ========== 库存查询 ==========
    def check_stock(self, product_id: str) -> dict:
        """查询库存"""
        if not self.beauty_kb:
            return {"in_stock": True, "stock": 100}

        product = self.beauty_kb.get_product_details(product_id)
        if not product:
            return {"in_stock": False, "error": "商品不存在"}

        stock = product.get("stock", 0)
        return {
            "in_stock": stock > 0,
            "stock": stock,
            "low_stock": stock < 50,
            "product_name": product.get("name"),
        }

    # ========== 价格保护 ==========
    def check_price_protection(self, order_id: str) -> dict:
        """价格保护检查"""
        order = self.orders.get(order_id)
        if not order:
            return {"error": "订单不存在"}

        # 检查订单中商品是否降价
        price_drops = []
        for item in order.items:
            if self.beauty_kb:
                product = self.beauty_kb.get_product_details(item.get("product_id"))
                if product and product["price"] < item.get("price", 0):
                    price_drops.append({
                        "product_id": item["product_id"],
                        "product_name": product["name"],
                        "original_price": item["price"],
                        "current_price": product["price"],
                        "drop_amount": item["price"] - product["price"],
                    })

        return {
            "order_id": order_id,
            "has_price_drop": len(price_drops) > 0,
            "price_drops": price_drops,
            "total_refund": sum(p["drop_amount"] for p in price_drops),
        }

    # ========== 订单统计 ==========
    def get_order_stats(self, user_id: str) -> dict:
        """用户订单统计"""
        user_orders = [o for o in self.orders.values() if o.user_id == user_id]

        return {
            "total_orders": len(user_orders),
            "pending": len([o for o in user_orders if o.status == "pending"]),
            "paid": len([o for o in user_orders if o.status == "paid"]),
            "shipped": len([o for o in user_orders if o.status == "shipped"]),
            "completed": len([o for o in user_orders if o.status == "completed"]),
            "total_spent": sum(o.total_amount for o in user_orders if o.status == "completed"),
        }
