"""
运营管理后台服务
统一管理：客户、商品、库存、订单、支付、物流、退款、用户、角色、配置
"""
import time
import uuid
from typing import Optional
from loguru import logger


class AdminService:
    """运营管理后台服务"""

    def __init__(self, beauty_kb=None, operations_manager=None):
        self.beauty_kb = beauty_kb
        self.ops = operations_manager

        # 各实体存储
        self.customers: dict = {}
        self.products: dict = {}      # 覆盖/扩展 beauty_kb
        self.inventory: dict = {}     # product_id -> {stock, warning_threshold}
        self.payments: dict = {}
        self.shipments: dict = {}
        self.refunds: dict = {}
        self.users: dict = {}         # 后台用户
        self.roles: dict = {}         # 角色
        self.configs: dict = {}       # 系统配置

        self._seed_data()
        logger.info("AdminService initialized")

    def _seed_data(self):
        """初始化演示数据"""
        # 从美妆知识库加载商品到管理存储
        if self.beauty_kb:
            for p in self.beauty_kb.products:
                self.products[p["id"]] = dict(p)
                self.inventory[p["id"]] = {
                    "product_id": p["id"],
                    "stock": p.get("stock", 0),
                    "warning_threshold": 50,
                    "updated_at": time.time(),
                }

        # 角色
        self.roles = {
            "role_admin": {"role_id": "role_admin", "name": "超级管理员",
                           "permissions": ["*"]},
            "role_ops": {"role_id": "role_ops", "name": "运营",
                         "permissions": ["product:read", "product:write", "order:read",
                                         "inventory:read", "inventory:write", "dashboard:read"]},
            "role_cs": {"role_id": "role_cs", "name": "客服",
                        "permissions": ["order:read", "refund:read", "refund:write",
                                        "customer:read", "ticket:write"]},
            "role_viewer": {"role_id": "role_viewer", "name": "只读",
                            "permissions": ["*:read"]},
        }

        # 后台用户
        self.users = {
            "user_admin": {"user_id": "user_admin", "username": "admin",
                           "name": "管理员", "role_id": "role_admin",
                           "status": "active", "created_at": time.time()},
            "user_ops01": {"user_id": "user_ops01", "username": "ops01",
                           "name": "运营小王", "role_id": "role_ops",
                           "status": "active", "created_at": time.time()},
            "user_cs01": {"user_id": "user_cs01", "username": "cs01",
                          "name": "客服小美", "role_id": "role_cs",
                          "status": "active", "created_at": time.time()},
        }

        # 系统配置
        self.configs = {
            "auto_escalation_threshold": {"key": "auto_escalation_threshold", "value": 3,
                                          "description": "连续未解决转人工阈值", "updated_at": time.time()},
            "session_ttl": {"key": "session_ttl", "value": 3600,
                            "description": "会话过期时间(秒)", "updated_at": time.time()},
            "max_history": {"key": "max_history", "value": 20,
                            "description": "最大历史消息数", "updated_at": time.time()},
            "promotion_enabled": {"key": "promotion_enabled", "value": True,
                                  "description": "是否启用大促模式", "updated_at": time.time()},
        }

        # 客户（示例）
        self.customers = {
            "cust_001": {"customer_id": "cust_001", "nickname": "张女士",
                         "phone": "138****8000", "level": "VIP",
                         "total_orders": 12, "total_spent": 8600.0,
                         "skin_type": "dry", "tags": ["VIP", "高价值"],
                         "created_at": time.time()},
            "cust_002": {"customer_id": "cust_002", "nickname": "李小姐",
                         "phone": "139****1234", "level": "normal",
                         "total_orders": 3, "total_spent": 1200.0,
                         "skin_type": "oily", "tags": ["新客"],
                         "created_at": time.time()},
        }

    # ==================================================================
    # 商品管理
    # ==================================================================
    def list_products(self, category: str = None, status: str = None,
                      keyword: str = None, page: int = 1, page_size: int = 20) -> dict:
        """商品列表"""
        items = list(self.products.values())
        if category:
            items = [p for p in items if p.get("category") == category]
        if status:
            items = [p for p in items if p.get("status") == status]
        if keyword:
            kw = keyword.lower()
            items = [p for p in items if kw in p.get("name", "").lower()
                     or kw in p.get("brand", "").lower()]

        total = len(items)
        start = (page - 1) * page_size
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items[start:start + page_size],
        }

    def get_product(self, product_id: str) -> Optional[dict]:
        return self.products.get(product_id)

    def create_product(self, data: dict) -> dict:
        """新增商品"""
        product_id = data.get("id") or f"prod_{uuid.uuid4().hex[:6]}"
        product = {
            "id": product_id,
            "name": data.get("name", ""),
            "brand": data.get("brand", ""),
            "category": data.get("category", ""),
            "subcategory": data.get("subcategory", ""),
            "price": float(data.get("price", 0)),
            "original_price": float(data.get("original_price", 0)),
            "description": data.get("description", ""),
            "ingredients": data.get("ingredients", []),
            "suitable_skin_types": data.get("suitable_skin_types", []),
            "stock": int(data.get("stock", 0)),
            "tags": data.get("tags", []),
            "status": data.get("status", "active"),
            "sales_count": 0,
            "rating": 5.0,
            "created_at": time.time(),
        }
        self.products[product_id] = product
        self.inventory[product_id] = {
            "product_id": product_id,
            "stock": product["stock"],
            "warning_threshold": 50,
            "updated_at": time.time(),
        }
        logger.info(f"Product created: {product_id}")
        return product

    def update_product(self, product_id: str, data: dict) -> dict:
        """更新商品"""
        product = self.products.get(product_id)
        if not product:
            return {"error": "商品不存在"}
        for key in ("name", "brand", "category", "subcategory", "description",
                    "ingredients", "suitable_skin_types", "tags", "status"):
            if key in data:
                product[key] = data[key]
        for key in ("price", "original_price"):
            if key in data:
                product[key] = float(data[key])
        product["updated_at"] = time.time()
        return product

    def delete_product(self, product_id: str) -> dict:
        """下架商品（软删除）"""
        product = self.products.get(product_id)
        if not product:
            return {"error": "商品不存在"}
        product["status"] = "inactive"
        return {"status": "inactive", "product_id": product_id}

    # ==================================================================
    # 库存管理
    # ==================================================================
    def list_inventory(self, low_stock_only: bool = False) -> list:
        """库存列表"""
        items = list(self.inventory.values())
        for item in items:
            product = self.products.get(item["product_id"])
            item["product_name"] = product.get("name") if product else ""
            item["low_stock"] = item["stock"] < item.get("warning_threshold", 50)
        if low_stock_only:
            items = [i for i in items if i["low_stock"]]
        return items

    def adjust_stock(self, product_id: str, delta: int = None, stock: int = None) -> dict:
        """调整库存（增减或直接设置）"""
        inv = self.inventory.get(product_id)
        if not inv:
            return {"error": "库存记录不存在"}

        if stock is not None:
            inv["stock"] = int(stock)
        elif delta is not None:
            inv["stock"] = max(0, inv["stock"] + int(delta))
        else:
            return {"error": "需提供 delta 或 stock"}

        inv["updated_at"] = time.time()
        # 同步到商品
        if product_id in self.products:
            self.products[product_id]["stock"] = inv["stock"]
        return inv

    def set_warning_threshold(self, product_id: str, threshold: int) -> dict:
        """设置库存预警阈值"""
        inv = self.inventory.get(product_id)
        if not inv:
            return {"error": "库存记录不存在"}
        inv["warning_threshold"] = int(threshold)
        return inv

    # ==================================================================
    # 订单管理
    # ==================================================================
    def list_orders(self, status: str = None, user_id: str = None) -> list:
        """订单列表"""
        if not self.ops:
            return []
        orders = list(self.ops.orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        if user_id:
            orders = [o for o in orders if o.user_id == user_id]
        return [o.__dict__ for o in orders]

    def get_order(self, order_id: str) -> Optional[dict]:
        if not self.ops:
            return None
        order = self.ops.get_order(order_id)
        return order.__dict__ if order else None

    def create_order(self, user_id: str, items: list, address: dict) -> dict:
        """创建订单"""
        if not self.ops:
            return {"error": "订单服务不可用"}
        order = self.ops.create_order(user_id, items, address)
        return order.__dict__

    def update_order_status(self, order_id: str, status: str) -> dict:
        """更新订单状态"""
        if not self.ops:
            return {"error": "订单服务不可用"}
        order = self.ops.get_order(order_id)
        if not order:
            return {"error": "订单不存在"}
        order.status = status
        return order.__dict__

    # ==================================================================
    # 支付管理
    # ==================================================================
    def record_payment(self, order_id: str, amount: float, method: str = "alipay") -> dict:
        """记录支付"""
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        payment = {
            "payment_id": payment_id,
            "order_id": order_id,
            "amount": float(amount),
            "method": method,
            "status": "success",
            "created_at": time.time(),
        }
        self.payments[payment_id] = payment
        return payment

    def list_payments(self, order_id: str = None, status: str = None) -> list:
        """支付列表"""
        items = list(self.payments.values())
        if order_id:
            items = [p for p in items if p["order_id"] == order_id]
        if status:
            items = [p for p in items if p["status"] == status]
        return items

    def refund_payment(self, payment_id: str, amount: float = None) -> dict:
        """支付退款"""
        payment = self.payments.get(payment_id)
        if not payment:
            return {"error": "支付记录不存在"}
        payment["status"] = "refunded"
        payment["refund_amount"] = amount if amount is not None else payment["amount"]
        payment["refunded_at"] = time.time()
        return payment

    # ==================================================================
    # 物流管理
    # ==================================================================
    def create_shipment(self, order_id: str, express_company: str,
                        tracking_number: str) -> dict:
        """创建发货单"""
        shipment_id = f"ship_{uuid.uuid4().hex[:8]}"
        shipment = {
            "shipment_id": shipment_id,
            "order_id": order_id,
            "express_company": express_company,
            "tracking_number": tracking_number,
            "status": "shipped",
            "created_at": time.time(),
        }
        self.shipments[shipment_id] = shipment
        # 同步订单
        if self.ops:
            self.ops.ship_order(order_id, tracking_number, express_company)
        return shipment

    def list_shipments(self, status: str = None) -> list:
        """物流列表"""
        items = list(self.shipments.values())
        if status:
            items = [s for s in items if s["status"] == status]
        return items

    def update_shipment_status(self, shipment_id: str, status: str) -> dict:
        """更新物流状态"""
        shipment = self.shipments.get(shipment_id)
        if not shipment:
            return {"error": "发货单不存在"}
        shipment["status"] = status
        shipment["updated_at"] = time.time()
        return shipment

    # ==================================================================
    # 退款管理
    # ==================================================================
    def list_refunds(self, status: str = None) -> list:
        """退款列表"""
        if not self.ops:
            return []
        refunds = list(self.ops.returns.values())
        if status:
            refunds = [r for r in refunds if r.status == status]
        return [r.__dict__ for r in refunds]

    def get_refund(self, return_id: str) -> Optional[dict]:
        if not self.ops:
            return None
        r = self.ops.returns.get(return_id)
        return r.__dict__ if r else None

    def approve_refund(self, return_id: str) -> dict:
        """审核通过退款"""
        if not self.ops:
            return {"error": "退款服务不可用"}
        result = self.ops.approve_return(return_id)
        # 同步支付退款
        if "error" not in result:
            refund = self.ops.returns.get(return_id)
            if refund:
                self.refunds[return_id] = {
                    "refund_id": return_id,
                    "order_id": refund.order_id,
                    "amount": refund.refund_amount,
                    "status": "approved",
                    "created_at": time.time(),
                }
        return result

    def reject_refund(self, return_id: str, reason: str) -> dict:
        """拒绝退款"""
        if not self.ops:
            return {"error": "退款服务不可用"}
        return self.ops.reject_return(return_id, reason)

    def complete_refund(self, return_id: str) -> dict:
        """完成退款"""
        if not self.ops:
            return {"error": "退款服务不可用"}
        return self.ops.complete_return(return_id)

    # ==================================================================
    # 客户管理
    # ==================================================================
    def list_customers(self, level: str = None, keyword: str = None) -> list:
        """客户列表"""
        items = list(self.customers.values())
        if level:
            items = [c for c in items if c.get("level") == level]
        if keyword:
            kw = keyword.lower()
            items = [c for c in items if kw in c.get("nickname", "").lower()]
        return items

    def get_customer(self, customer_id: str) -> Optional[dict]:
        return self.customers.get(customer_id)

    def create_customer(self, data: dict) -> dict:
        """新增客户"""
        customer_id = data.get("customer_id") or f"cust_{uuid.uuid4().hex[:6]}"
        customer = {
            "customer_id": customer_id,
            "nickname": data.get("nickname", ""),
            "phone": data.get("phone", ""),
            "level": data.get("level", "normal"),
            "total_orders": 0,
            "total_spent": 0.0,
            "skin_type": data.get("skin_type"),
            "tags": data.get("tags", []),
            "created_at": time.time(),
        }
        self.customers[customer_id] = customer
        return customer

    def update_customer(self, customer_id: str, data: dict) -> dict:
        """更新客户"""
        customer = self.customers.get(customer_id)
        if not customer:
            return {"error": "客户不存在"}
        for key in ("nickname", "phone", "level", "skin_type", "tags"):
            if key in data:
                customer[key] = data[key]
        customer["updated_at"] = time.time()
        return customer

    def delete_customer(self, customer_id: str) -> dict:
        """删除客户"""
        if customer_id not in self.customers:
            return {"error": "客户不存在"}
        self.customers.pop(customer_id)
        return {"status": "deleted", "customer_id": customer_id}

    # ==================================================================
    # 用户管理（后台账号）
    # ==================================================================
    def list_users(self) -> list:
        return list(self.users.values())

    def create_user(self, username: str, name: str, role_id: str) -> dict:
        """创建后台用户"""
        if any(u["username"] == username for u in self.users.values()):
            return {"error": "用户名已存在"}
        user_id = f"user_{uuid.uuid4().hex[:6]}"
        user = {
            "user_id": user_id,
            "username": username,
            "name": name,
            "role_id": role_id,
            "status": "active",
            "created_at": time.time(),
        }
        self.users[user_id] = user
        return user

    def update_user(self, user_id: str, data: dict) -> dict:
        """更新后台用户"""
        user = self.users.get(user_id)
        if not user:
            return {"error": "用户不存在"}
        for key in ("name", "role_id", "status"):
            if key in data:
                user[key] = data[key]
        return user

    def delete_user(self, user_id: str) -> dict:
        """删除后台用户"""
        if user_id not in self.users:
            return {"error": "用户不存在"}
        self.users.pop(user_id)
        return {"status": "deleted", "user_id": user_id}

    # ==================================================================
    # 角色管理
    # ==================================================================
    def list_roles(self) -> list:
        return list(self.roles.values())

    def create_role(self, name: str, permissions: list) -> dict:
        """创建角色"""
        role_id = f"role_{uuid.uuid4().hex[:6]}"
        role = {
            "role_id": role_id,
            "name": name,
            "permissions": permissions,
            "created_at": time.time(),
        }
        self.roles[role_id] = role
        return role

    def update_role(self, role_id: str, data: dict) -> dict:
        """更新角色"""
        role = self.roles.get(role_id)
        if not role:
            return {"error": "角色不存在"}
        for key in ("name", "permissions"):
            if key in data:
                role[key] = data[key]
        return role

    def delete_role(self, role_id: str) -> dict:
        """删除角色"""
        if role_id not in self.roles:
            return {"error": "角色不存在"}
        # 检查是否有用户使用
        if any(u["role_id"] == role_id for u in self.users.values()):
            return {"error": "该角色仍被用户使用，无法删除"}
        self.roles.pop(role_id)
        return {"status": "deleted", "role_id": role_id}

    def has_permission(self, user_id: str, permission: str) -> bool:
        """检查用户权限"""
        user = self.users.get(user_id)
        if not user:
            return False
        role = self.roles.get(user["role_id"])
        if not role:
            return False
        perms = role.get("permissions", [])
        if "*" in perms:
            return True
        if permission in perms:
            return True
        # 通配 *:read
        resource = permission.split(":")[0]
        if f"{resource}:*" in perms:
            return True
        if f"*:{permission.split(':')[-1]}" in perms:
            return True
        return False

    # ==================================================================
    # 配置管理
    # ==================================================================
    def list_configs(self) -> list:
        return list(self.configs.values())

    def get_config(self, key: str) -> Optional[dict]:
        return self.configs.get(key)

    def set_config(self, key: str, value, description: str = None) -> dict:
        """设置配置"""
        if key in self.configs:
            self.configs[key]["value"] = value
            if description:
                self.configs[key]["description"] = description
            self.configs[key]["updated_at"] = time.time()
        else:
            self.configs[key] = {
                "key": key,
                "value": value,
                "description": description or "",
                "updated_at": time.time(),
            }
        return self.configs[key]

    def delete_config(self, key: str) -> dict:
        """删除配置"""
        if key not in self.configs:
            return {"error": "配置不存在"}
        self.configs.pop(key)
        return {"status": "deleted", "key": key}

    # ==================================================================
    # 后台总览
    # ==================================================================
    def get_overview(self) -> dict:
        """后台总览统计"""
        return {
            "products": {
                "total": len(self.products),
                "active": sum(1 for p in self.products.values() if p.get("status") == "active"),
            },
            "inventory": {
                "total_skus": len(self.inventory),
                "low_stock": sum(1 for i in self.inventory.values()
                                 if i["stock"] < i.get("warning_threshold", 50)),
            },
            "orders": {
                "total": len(self.ops.orders) if self.ops else 0,
            },
            "refunds": {
                "total": len(self.ops.returns) if self.ops else 0,
                "pending": sum(1 for r in self.ops.returns.values() if r.status == "pending") if self.ops else 0,
            },
            "customers": {"total": len(self.customers)},
            "users": {"total": len(self.users)},
            "roles": {"total": len(self.roles)},
        }
