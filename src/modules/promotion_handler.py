"""
大促场景模块
支持预售/满减/秒杀/拼团/优惠券等大促逻辑
"""
import time
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class PromotionContext:
    """大促上下文"""
    promotion_id: Optional[str] = None
    promotion_type: Optional[str] = None  # presale/flash_sale/full_reduction/group_buy/coupon
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    discount_rules: dict = field(default_factory=dict)
    applicable_products: list = field(default_factory=list)
    per_user_limit: Optional[int] = None
    stock_limit: Optional[int] = None
    current_stock: int = 0


class PromotionHandler:
    """大促处理器"""

    def __init__(self, beauty_kb=None):
        self.beauty_kb = beauty_kb
        self.active_promotions: dict = {}
        self.presale_orders: dict = {}  # 预售订单
        logger.info("PromotionHandler initialized")

    def is_promotion_active(self, promotion_id: str) -> bool:
        """检查活动是否进行中"""
        promo = self.active_promotions.get(promotion_id)
        if not promo:
            return False
        now = time.time()
        return promo["start_time"] <= now <= promo["end_time"]

    def calculate_discount(self, product_id: str, quantity: int, promotion_id: str = None) -> dict:
        """计算折扣后价格"""
        result = {
            "original_price": 0.0,
            "discount_price": 0.0,
            "discount_amount": 0.0,
            "applied_rules": [],
        }

        if not self.beauty_kb:
            return result

        product = self.beauty_kb.get_product_details(product_id)
        if not product:
            return result

        original_price = product["price"]
        result["original_price"] = original_price
        result["discount_price"] = original_price

        # 应用促销规则
        if promotion_id and promotion_id in self.active_promotions:
            promo = self.active_promotions[promotion_id]
            rules = promo.get("rules", {})

            if promo["type"] == "full_reduction":
                # 满减：满X减Y
                threshold = rules.get("threshold", 0)
                reduction = rules.get("reduction", 0)
                if original_price * quantity >= threshold:
                    result["discount_price"] = original_price - reduction
                    result["applied_rules"].append(f"满{threshold}减{reduction}")

            elif promo["type"] == "flash_sale":
                # 秒杀价
                flash_price = rules.get("flash_price", original_price)
                result["discount_price"] = flash_price
                result["applied_rules"].append(f"秒杀价{flash_price}")

            elif promo["type"] == "presale":
                # 预售：定金膨胀
                deposit = rules.get("deposit", 0)
                deposit_discount = rules.get("deposit_discount", 0)
                final_price = rules.get("final_price", original_price)
                result["discount_price"] = final_price
                result["applied_rules"].append(f"定金{deposit}抵{deposit + deposit_discount}")

            elif promo["type"] == "group_buy":
                # 拼团
                group_price = rules.get("group_price", original_price)
                min_group_size = rules.get("min_group_size", 2)
                if quantity >= min_group_size:
                    result["discount_price"] = group_price
                    result["applied_rules"].append(f"{min_group_size}人拼团价{group_price}")

        result["discount_amount"] = result["original_price"] - result["discount_price"]
        return result

    def create_presale_order(self, user_id: str, product_id: str, deposit: float, promotion_id: str) -> dict:
        """创建预售订单"""
        order_id = f"PS{int(time.time())}{user_id[-4:]}"
        self.presale_orders[order_id] = {
            "user_id": user_id,
            "product_id": product_id,
            "deposit": deposit,
            "promotion_id": promotion_id,
            "status": "deposit_paid",
            "created_at": time.time(),
        }
        return {"order_id": order_id, "status": "deposit_paid", "deposit": deposit}

    def pay_final(self, order_id: str) -> dict:
        """支付尾款"""
        if order_id not in self.presale_orders:
            return {"error": "订单不存在"}

        order = self.presale_orders[order_id]
        if order["status"] != "deposit_paid":
            return {"error": "订单状态错误"}

        order["status"] = "completed"
        return {"order_id": order_id, "status": "completed"}

    def get_promotion_script(self, scene: str, emotion_type: str = None, variables: dict = None) -> str:
        """获取大促话术"""
        if self.beauty_kb:
            return self.beauty_kb.get_promotion_script(scene, emotion_type, variables)
        return ""

    def check_purchase_limit(self, user_id: str, product_id: str, promotion_id: str) -> dict:
        """检查限购"""
        if promotion_id not in self.active_promotions:
            return {"can_buy": True}

        promo = self.active_promotions[promotion_id]
        limit = promo.get("per_user_limit")

        if limit is None:
            return {"can_buy": True}

        # TODO: 查询用户已购数量
        purchased = 0
        return {
            "can_buy": purchased < limit,
            "limit": limit,
            "purchased": purchased,
            "remaining": max(0, limit - purchased),
        }

    def check_stock(self, product_id: str, promotion_id: str = None) -> dict:
        """检查库存"""
        if not self.beauty_kb:
            return {"in_stock": True}

        product = self.beauty_kb.get_product_details(product_id)
        if not product:
            return {"in_stock": False, "error": "商品不存在"}

        stock = product.get("stock", 0)
        return {
            "in_stock": stock > 0,
            "stock": stock,
            "low_stock": stock < 50,
        }
