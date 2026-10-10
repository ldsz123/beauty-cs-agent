"""
业务动作执行器
根据意图执行对应的业务操作
"""
from typing import Optional
from loguru import logger


class BusinessActionExecutor:
    """
    业务动作执行器
    根据意图和实体执行具体业务操作
    MVP 阶段返回模拟数据，生产环境对接真实 API
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        logger.info("BusinessActionExecutor initialized")
    
    async def execute(self, intent, entities, session: dict = None) -> list[dict]:
        """根据意图执行对应业务动作"""
        from ..layers.semantic_layer import IntentType
        
        action_map = {
            IntentType.ORDER_STATUS: self._query_order,
            IntentType.SHIPPING_INQUIRY: self._query_logistics,
            IntentType.RETURN_REFUND: self._initiate_return,
            IntentType.PRODUCT_INQUIRY: self._query_product,
            IntentType.PRICE_INQUIRY: self._query_price,
            IntentType.PAYMENT_ISSUE: self._handle_payment_issue,
            IntentType.ORDER_MODIFY: self._modify_order,
            IntentType.EXCHANGE: self._initiate_exchange,
            IntentType.COMPLAINT: self._handle_complaint,
            IntentType.PROMOTION_INQUIRY: self._query_promotion,
            IntentType.ACCOUNT_ISSUE: self._handle_account_issue,
        }
        
        handler = action_map.get(intent)
        if handler:
            return await handler(entities, session)
        return []
    
    async def _query_order(self, entities, session):
        """查询订单"""
        order_id = entities.order_id or (session or {}).get("last_order_id")
        if order_id:
            # TODO: 对接真实订单 API
            return [{"action": "query_order", "status": "success",
                     "data": {"order_id": order_id, "status": "已发货",
                              "items": ["示例商品 x1"], "total": "￥199.00"}}]
        return [{"action": "query_order", "status": "need_order_id"}]
    
    async def _query_logistics(self, entities, session):
        """查询物流"""
        tracking = entities.tracking_number or entities.order_id
        if tracking:
            return [{"action": "query_logistics", "status": "success",
                     "data": {"tracking_no": tracking, "status": "运输中",
                              "latest_update": "【北京】已发往上海",
                              "estimated_delivery": "预计明天送达"}}]
        return [{"action": "query_logistics", "status": "need_tracking_number"}]
    
    async def _initiate_return(self, entities, session):
        """发起退货"""
        if entities.order_id:
            return [{"action": "initiate_return", "status": "created",
                     "data": {"order_id": entities.order_id,
                              "return_id": "RT202401010001",
                              "status": "待审核",
                              "message": "退货申请已提交，预计1-3个工作日审核"}}]
        return [{"action": "initiate_return", "status": "need_order_id"}]
    
    async def _query_product(self, entities, session):
        """查询商品"""
        if entities.product_name or entities.product_sku:
            return [{"action": "query_product", "status": "success",
                     "data": {"name": entities.product_name or "商品名称",
                              "price": "￥199.00", "stock": "有货",
                              "description": "商品详情描述"}}]
        return [{"action": "query_product", "status": "need_product_info"}]
    
    async def _query_price(self, entities, session):
        """查询价格"""
        return [{"action": "query_price", "status": "success",
                 "data": {"price": "￥199.00", "original_price": "￥299.00",
                          "discount": "限时7折"}}]
    
    async def _handle_payment_issue(self, entities, session):
        """处理支付问题"""
        return [{"action": "handle_payment_issue", "status": "guidance",
                 "message": "请检查：1.网络连接 2.支付余额 3.银行卡限额"}]
    
    async def _modify_order(self, entities, session):
        """修改订单"""
        if entities.order_id:
            return [{"action": "modify_order", "status": "pending",
                     "message": "请提供需要修改的内容（地址/手机号）"}]
        return [{"action": "modify_order", "status": "need_order_id"}]
    
    async def _initiate_exchange(self, entities, session):
        """发起换货"""
        if entities.order_id:
            return [{"action": "initiate_exchange", "status": "created",
                     "data": {"order_id": entities.order_id,
                              "exchange_id": "EX202401010001",
                              "status": "待审核"}}]
        return [{"action": "initiate_exchange", "status": "need_order_id"}]
    
    async def _handle_complaint(self, entities, session):
        """处理投诉"""
        return [{"action": "handle_complaint", "status": "recorded",
                 "data": {"complaint_id": "CP202401010001",
                          "priority": "high",
                          "message": "您的投诉已记录，专员将在24小时内联系您"}}]
    
    async def _query_promotion(self, entities, session):
        """查询促销活动"""
        return [{"action": "query_promotion", "status": "success",
                 "data": {"current_promotions": [
                     {"name": "新用户首单减10", "code": "NEW10"},
                     {"name": "满199减30", "code": "SAVE30"},
                 ]}}]
    
    async def _handle_account_issue(self, entities, session):
        """处理账户问题"""
        return [{"action": "handle_account_issue", "status": "guidance",
                 "message": "账户问题请提供具体描述，如：登录异常/密码找回/绑定手机等"}]
