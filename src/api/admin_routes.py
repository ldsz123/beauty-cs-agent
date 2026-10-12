"""
运营管理后台 API 路由
商品 / 库存 / 订单 / 支付 / 物流 / 退款 / 客户 / 用户 / 角色 / 配置
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from .state import state


router = APIRouter(prefix="/api/admin", tags=["admin"])


def _admin():
    """获取管理服务"""
    if not state.agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return state.agent.admin_service


# ==================== 总览 ====================
@router.get("/overview")
async def overview():
    return _admin().get_overview()


# ==================== 商品 ====================
class ProductIn(BaseModel):
    name: str
    brand: str = ""
    category: str = ""
    subcategory: str = ""
    price: float = 0.0
    original_price: float = 0.0
    description: str = ""
    ingredients: list = []
    suitable_skin_types: list = []
    stock: int = 0
    tags: list = []
    status: str = "active"


@router.get("/products")
async def list_products(category: str = None, status: str = None,
                        keyword: str = None, page: int = 1, page_size: int = 20):
    return _admin().list_products(category, status, keyword, page, page_size)


@router.get("/products/{product_id}")
async def get_product(product_id: str):
    p = _admin().get_product(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    return p


@router.post("/products")
async def create_product(data: ProductIn):
    return _admin().create_product(data.model_dump())


@router.put("/products/{product_id}")
async def update_product(product_id: str, data: dict):
    result = _admin().update_product(product_id, data)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/products/{product_id}")
async def delete_product(product_id: str):
    result = _admin().delete_product(product_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ==================== 库存 ====================
@router.get("/inventory")
async def list_inventory(low_stock_only: bool = False):
    return {"items": _admin().list_inventory(low_stock_only)}


@router.post("/inventory/{product_id}/adjust")
async def adjust_stock(product_id: str, delta: int = None, stock: int = None):
    result = _admin().adjust_stock(product_id, delta, stock)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/inventory/{product_id}/threshold")
async def set_threshold(product_id: str, threshold: int):
    result = _admin().set_warning_threshold(product_id, threshold)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ==================== 订单 ====================
@router.get("/orders")
async def list_orders(status: str = None, user_id: str = None):
    return {"items": _admin().list_orders(status, user_id)}


@router.get("/orders/{order_id}")
async def get_order(order_id: str):
    o = _admin().get_order(order_id)
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    return o


class OrderIn(BaseModel):
    user_id: str
    items: list
    address: dict


@router.post("/orders")
async def create_order(data: OrderIn):
    return _admin().create_order(data.user_id, data.items, data.address)


@router.put("/orders/{order_id}/status")
async def update_order_status(order_id: str, status: str):
    result = _admin().update_order_status(order_id, status)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ==================== 支付 ====================
@router.get("/payments")
async def list_payments(order_id: str = None, status: str = None):
    return {"items": _admin().list_payments(order_id, status)}


@router.post("/payments")
async def record_payment(order_id: str, amount: float, method: str = "alipay"):
    return _admin().record_payment(order_id, amount, method)


@router.post("/payments/{payment_id}/refund")
async def refund_payment(payment_id: str, amount: float = None):
    result = _admin().refund_payment(payment_id, amount)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ==================== 物流 ====================
@router.get("/shipments")
async def list_shipments(status: str = None):
    return {"items": _admin().list_shipments(status)}


@router.post("/shipments")
async def create_shipment(order_id: str, express_company: str, tracking_number: str):
    return _admin().create_shipment(order_id, express_company, tracking_number)


@router.put("/shipments/{shipment_id}/status")
async def update_shipment_status(shipment_id: str, status: str):
    result = _admin().update_shipment_status(shipment_id, status)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ==================== 退款 ====================
@router.get("/refunds")
async def list_refunds(status: str = None):
    return {"items": _admin().list_refunds(status)}


@router.get("/refunds/{return_id}")
async def get_refund(return_id: str):
    r = _admin().get_refund(return_id)
    if not r:
        raise HTTPException(status_code=404, detail="Refund not found")
    return r


@router.post("/refunds/{return_id}/approve")
async def approve_refund(return_id: str):
    return _admin().approve_refund(return_id)


@router.post("/refunds/{return_id}/reject")
async def reject_refund(return_id: str, reason: str):
    return _admin().reject_refund(return_id, reason)


@router.post("/refunds/{return_id}/complete")
async def complete_refund(return_id: str):
    return _admin().complete_refund(return_id)


# ==================== 客户 ====================
class CustomerIn(BaseModel):
    nickname: str
    phone: str = ""
    level: str = "normal"
    skin_type: Optional[str] = None
    tags: list = []


@router.get("/customers")
async def list_customers(level: str = None, keyword: str = None):
    return {"items": _admin().list_customers(level, keyword)}


@router.get("/customers/{customer_id}")
async def get_customer(customer_id: str):
    c = _admin().get_customer(customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    return c


@router.post("/customers")
async def create_customer(data: CustomerIn):
    return _admin().create_customer(data.model_dump())


@router.put("/customers/{customer_id}")
async def update_customer(customer_id: str, data: dict):
    result = _admin().update_customer(customer_id, data)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str):
    result = _admin().delete_customer(customer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ==================== 用户 ====================
class UserIn(BaseModel):
    username: str
    name: str
    role_id: str


@router.get("/users")
async def list_users():
    return {"items": _admin().list_users()}


@router.post("/users")
async def create_user(data: UserIn):
    result = _admin().create_user(data.username, data.name, data.role_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.put("/users/{user_id}")
async def update_user(user_id: str, data: dict):
    result = _admin().update_user(user_id, data)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    result = _admin().delete_user(user_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ==================== 角色 ====================
class RoleIn(BaseModel):
    name: str
    permissions: list


@router.get("/roles")
async def list_roles():
    return {"items": _admin().list_roles()}


@router.post("/roles")
async def create_role(data: RoleIn):
    return _admin().create_role(data.name, data.permissions)


@router.put("/roles/{role_id}")
async def update_role(role_id: str, data: dict):
    result = _admin().update_role(role_id, data)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str):
    result = _admin().delete_role(role_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ==================== 配置 ====================
class ConfigIn(BaseModel):
    value: object
    description: str = ""


@router.get("/configs")
async def list_configs():
    return {"items": _admin().list_configs()}


@router.get("/configs/{key}")
async def get_config(key: str):
    c = _admin().get_config(key)
    if not c:
        raise HTTPException(status_code=404, detail="Config not found")
    return c


@router.put("/configs/{key}")
async def set_config(key: str, data: ConfigIn):
    return _admin().set_config(key, data.value, data.description)


@router.delete("/configs/{key}")
async def delete_config(key: str):
    result = _admin().delete_config(key)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
