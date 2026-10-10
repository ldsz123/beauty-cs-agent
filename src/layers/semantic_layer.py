"""
语义分类层 — 第二级处理
基于 LLM 的意图识别，结合情感上下文调整分类
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


class IntentType(Enum):
    """电商客服意图分类"""
    # 售前咨询
    PRODUCT_INQUIRY = "product_inquiry"
    PRICE_INQUIRY = "price_inquiry"
    PROMOTION_INQUIRY = "promotion_inquiry"
    COMPARISON = "comparison"
    
    # 售中服务
    ORDER_STATUS = "order_status"
    ORDER_MODIFY = "order_modify"
    PAYMENT_ISSUE = "payment_issue"
    SHIPPING_INQUIRY = "shipping_inquiry"
    
    # 售后服务
    RETURN_REFUND = "return_refund"
    EXCHANGE = "exchange"
    COMPLAINT = "complaint"
    WARRANTY = "warranty"
    
    # 其他
    ACCOUNT_ISSUE = "account_issue"
    TECH_SUPPORT = "tech_support"
    GENERAL_CHAT = "general_chat"
    ESCALATE = "escalate"


class UrgencyLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SemanticResult:
    primary_intent: IntentType = IntentType.GENERAL_CHAT
    secondary_intents: list = field(default_factory=list)
    confidence: float = 0.0
    urgency: UrgencyLevel = UrgencyLevel.LOW
    context_dependencies: list = field(default_factory=list)
    required_info: list = field(default_factory=list)
    reasoning: str = ""


class SemanticClassificationLayer:
    """语义分类层"""
    
    def __init__(self, llm_client=None, intent_examples_path: str = None):
        self.llm = llm_client
        self.intent_examples = {}
        if intent_examples_path:
            self._load_intent_examples(intent_examples_path)
        
        logger.info("SemanticClassificationLayer initialized")
    
    def _load_intent_examples(self, path: str):
        import json
        from pathlib import Path
        try:
            p = Path(path)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    self.intent_examples = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load intent examples: {e}")
    
    async def classify(self, user_message: str,
                       emotion_result=None,
                       conversation_context: dict = None) -> SemanticResult:
        """语义分类"""
        context_info = ""
        if emotion_result:
            context_info = f"\n用户情感状态：{emotion_result.emotion.value}（强度：{emotion_result.intensity.value}）"
        
        prompt = f"""你是电商客服意图识别专家。请分析用户消息的意图。

用户消息：{user_message}
{context_info}

意图类别（选择最匹配的一个作为主意图）：
售前：product_inquiry(商品咨询), price_inquiry(价格), promotion_inquiry(促销), comparison(对比)
售中：order_status(订单查询), order_modify(订单修改), payment_issue(支付问题), shipping_inquiry(物流查询)
售后：return_refund(退货退款), exchange(换货), complaint(投诉), warranty(保修)
其他：account_issue(账户问题), tech_support(技术支持), general_chat(闲聊), escalate(转人工)

返回JSON：
{{"primary_intent": "主意图", "secondary_intents": ["次要意图"], "confidence": 0.0-1.0, "urgency": "low/medium/high/critical", "context_dependencies": ["依赖信息"], "required_info": ["需补充的信息"], "reasoning": "分类理由"}}"""

        try:
            if self.llm:
                response = await self.llm.chat(prompt, response_format="json")
            else:
                # 无 LLM 时的 fallback
                return self._fallback_classify(user_message, emotion_result)
            
            # 调整紧急程度
            urgency = self._adjust_urgency(
                UrgencyLevel(response.get("urgency", "low")),
                emotion_result
            )
            
            return SemanticResult(
                primary_intent=IntentType(response.get("primary_intent", "general_chat")),
                secondary_intents=[
                    IntentType(i) for i in response.get("secondary_intents", [])
                    if i in [e.value for e in IntentType]
                ],
                confidence=response.get("confidence", 0.5),
                urgency=urgency,
                context_dependencies=response.get("context_dependencies", []),
                required_info=response.get("required_info", []),
                reasoning=response.get("reasoning", "")
            )
        except Exception as e:
            logger.error(f"Semantic classification failed: {e}")
            return self._fallback_classify(user_message, emotion_result)
    
    def _fallback_classify(self, message: str, emotion_result) -> SemanticResult:
        """无 LLM 时的规则 fallback"""
        import re
        
        intent_keywords = {
            IntentType.ORDER_STATUS: ["订单", "查到", "查询订单", "我的订单", "下单"],
            IntentType.SHIPPING_INQUIRY: ["物流", "快递", "发货", "送到", "在哪", "到哪", "配送",
                                          "运费", "包邮", "邮费", "发货时间", "多久能到"],
            IntentType.RETURN_REFUND: ["退货", "退款", "退掉", "不想要", "退回"],
            IntentType.EXCHANGE: ["换货", "换一个", "换款", "换色", "换尺码"],
            IntentType.COMPLAINT: ["投诉", "举报", "315", "消协", "太差"],
            IntentType.WARRANTY: ["保修", "质量", "坏了", "故障", "维修"],
            IntentType.PRICE_INQUIRY: ["多少钱", "价格", "费用", "优惠", "打折"],
            IntentType.PRODUCT_INQUIRY: ["有吗", "有没有", "商品详情", "介绍", "规格", "参数"],
            IntentType.PAYMENT_ISSUE: ["支付", "付款", "付不了", "扣款", "支付失败"],
            IntentType.PROMOTION_INQUIRY: ["活动", "优惠", "满减", "优惠券", "红包", "折扣"],
            IntentType.ACCOUNT_ISSUE: ["账号", "登录", "密码", "注册", "绑定"],
            IntentType.ESCALATE: ["人工", "找客服", "转人工", "真人"],
        }
        
        # 表扬/好评类消息优先归为闲聊（避免"商品不错"误判为商品咨询）
        praise_words = ["好评", "很满意", "不错", "物超所值", "五星", "很棒", "给力"]
        if any(w in message for w in praise_words):
            return SemanticResult(
                primary_intent=IntentType.GENERAL_CHAT,
                confidence=0.7,
                urgency=UrgencyLevel.LOW,
                reasoning="表扬/好评类消息"
            )
        
        for intent, keywords in intent_keywords.items():
            for kw in keywords:
                if kw in message:
                    return SemanticResult(
                        primary_intent=intent,
                        confidence=0.6,
                        urgency=UrgencyLevel.HIGH if emotion_result and emotion_result.emotion.value == "angry" else UrgencyLevel.MEDIUM,
                        reasoning=f"关键词匹配: {kw}"
                    )
        
        return SemanticResult(
            primary_intent=IntentType.GENERAL_CHAT,
            confidence=0.3,
            urgency=UrgencyLevel.LOW
        )
    
    def _adjust_urgency(self, base: UrgencyLevel, emotion) -> UrgencyLevel:
        """根据情感调整紧急度"""
        if emotion and emotion.emotion.value in ["angry", "urgent"]:
            if emotion.intensity.value >= 3:
                return UrgencyLevel.CRITICAL
            elif emotion.intensity.value >= 2:
                return UrgencyLevel.HIGH
        return base
