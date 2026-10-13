"""
智能路由引擎
决定消息走 业务查询 / 知识问答 / 混合 / 澄清 / 人工 / 闲聊，
并提取槽位与白名单动作。参考 AgentServe 的路由设计：
- route 与 intent 必须一致
- 写操作只能来自白名单动作（服务器再校验权限）
- 歧义指代（"有个订单"）先澄清
"""
import os
import re
import json
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger


# ========== 路由常量 ==========
ROUTES = ("business", "knowledge", "hybrid", "clarify", "human", "chitchat")

# 每个 route 允许的 intent
ROUTE_INTENTS = {
    "business": {"order_query", "shipping_query", "refund_query", "product_query",
                 "business_action", "refund_eligibility"},
    "knowledge": {"knowledge"},
    "hybrid": {"refund_eligibility", "order_query", "shipping_query", "product_query"},
    "clarify": {"clarify"},
    "human": {"human"},
    "chitchat": {"chitchat"},
}

# 白名单写操作（服务器端必须再校验权限）
ALLOWED_ACTIONS = {"cancel_order", "apply_refund"}

# 歧义指代词（缺少订单号时先澄清）
AMBIGUOUS_ORDER_WORDS = (
    "有个订单", "一个订单", "某个订单", "这两个订单", "两笔订单",
    "多个订单", "几个订单", "那个订单",
)

# 最新订单指代
LATEST_ORDER_CUES = ("刚下单", "刚刚下单", "刚才下单", "刚买", "刚刚买", "最近下单", "最新订单", "最近订单")

# 政策/规则类问题 → 知识
POLICY_WORDS = ("政策", "规则", "条件", "标准", "流程", "怎么", "如何", "能不能", "可以吗", "是否", "多久", "几天")

# 明确要求人工
HUMAN_WORDS = ("人工", "转人工", "找客服", "真人", "人工客服")


@dataclass
class RoutingDecision:
    """路由决策"""
    route: str = "chitchat"
    intent: str = "chitchat"
    order_id: Optional[str] = None
    product_sku: Optional[str] = None
    product_query: Optional[str] = None
    product_field: str = "info"           # price / inventory / info
    action: Optional[str] = None          # cancel_order / apply_refund
    question: Optional[str] = None        # 澄清时向用户提的问题
    knowledge_query: Optional[str] = None
    reason: str = ""
    decided_by: str = "rule"              # rule / llm

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "intent": self.intent,
            "order_id": self.order_id,
            "product_sku": self.product_sku,
            "product_query": self.product_query,
            "product_field": self.product_field,
            "action": self.action,
            "question": self.question,
            "knowledge_query": self.knowledge_query,
            "reason": self.reason,
            "decided_by": self.decided_by,
        }

    def validate(self) -> bool:
        """route 与 intent 一致性校验"""
        return self.intent in ROUTE_INTENTS.get(self.route, set())


class RoutingEngine:
    """智能路由引擎"""

    def __init__(self, llm_client=None):
        self.llm = llm_client
        # 默认走规则路由（快、确定）；设 LLM_ROUTING=true 启用模型路由
        self.use_llm = (
            llm_client is not None
            and os.environ.get("LLM_ROUTING", "false").lower() == "true"
        )
        self._stats = {"business": 0, "knowledge": 0, "hybrid": 0,
                       "clarify": 0, "human": 0, "chitchat": 0}
        logger.info(f"RoutingEngine initialized (llm_routing={self.use_llm})")

    # ========== 槽位提取（确定性规则） ==========
    @staticmethod
    def extract_order_ids(text: str) -> list[str]:
        """提取订单号（支持 ESH-/DEMO-/PDD- 前缀及"订单号"标记）"""
        ids = list(dict.fromkeys(
            v.upper() for v in re.findall(
                r"(?<![A-Za-z0-9_-])(?:ESH|DEMO|PDD|TB|ORD)-[A-Za-z0-9_-]{3,64}(?![A-Za-z0-9_-])",
                text, re.I)
        ))
        if ids:
            return ids
        m = re.search(r"(?:订单[号#：:\s]*|order[\s#:]*)([A-Za-z0-9_-]{3,64})", text, re.I)
        return [m.group(1)] if m else []

    @staticmethod
    def extract_product_sku(text: str) -> Optional[str]:
        """提取商品 SKU"""
        full = re.search(r"(?<![A-Za-z0-9_-])SKU-[A-Za-z0-9_-]+", text, re.I)
        if full:
            return full.group(0)
        m = re.search(r"(?:商品(?:编号|号|ID)?|SKU)[#：:\s]*([A-Za-z0-9_-]{3,64})", text, re.I)
        return m.group(1) if m else None

    # ========== 守卫规则（确定性，优先于 LLM） ==========
    def _guard(self, text: str) -> Optional[RoutingDecision]:
        """返回非空表示规则已确定路由"""
        t = text.lower()

        # 1. 明确要求人工
        if any(w in t for w in HUMAN_WORDS):
            return RoutingDecision(
                route="human", intent="human",
                reason="用户明确要求人工", decided_by="rule",
            )

        # 2. 歧义指代（无订单号）→ 澄清
        order_ids = self.extract_order_ids(text)
        if any(w in t for w in AMBIGUOUS_ORDER_WORDS) and not order_ids:
            return RoutingDecision(
                route="clarify", intent="clarify",
                question="请问您说的是哪个订单呢？麻烦提供一下订单号，我好帮您查询。",
                reason="订单指代不明确", decided_by="rule",
            )

        # 3. 商家/退货地址类通用问题 → 知识（非个人订单地址）
        if any(w in t for w in ("收货地址", "收件地址", "退货地址", "寄回地址", "寄件地址")):
            if not any(w in t for w in ("我的订单", "订单地址", "我填写的", "我填的", "我下单时", "我的收货地址", "我的地址")):
                return RoutingDecision(
                    route="knowledge", intent="knowledge",
                    knowledge_query=text, reason="通用地址政策咨询", decided_by="rule",
                )

        return None

    # ========== LLM 路由 ==========
    async def _llm_route(self, text: str, context: dict = None) -> Optional[RoutingDecision]:
        """调用 LLM 做路由决策"""
        if not self.llm:
            return None

        ctx = json.dumps(context or {}, ensure_ascii=False)
        prompt = f"""你是电商客服智能路由专家。请判断用户消息应该走哪条处理路径。

用户消息：{text}
会话上下文：{ctx}

路由类型（route）：
- business: 需要查询业务数据（订单/物流/退款/商品/库存）
- knowledge: 需要查询知识库（政策/规则/流程/说明）
- hybrid: 既要查业务数据又要查知识（如"我这个订单能退吗"）
- clarify: 信息不足，需要向用户追问（如订单指代不明）
- human: 需要人工客服介入
- chitchat: 闲聊/问候/感谢

意图（intent）必须与 route 匹配：
business → order_query/shipping_query/refund_query/product_query/business_action/refund_eligibility
knowledge → knowledge
hybrid → refund_eligibility/order_query/shipping_query/product_query
clarify → clarify
human → human
chitchat → chitchat

白名单写操作（action，仅 business_action 时填写，其他为 null）：
cancel_order(取消订单) / apply_refund(申请退款)

严格返回JSON：
{{"route":"...","intent":"...","order_id":null,"product_sku":null,"product_query":null,"product_field":"info","action":null,"question":null,"knowledge_query":null}}"""

        try:
            result = await self.llm.chat(prompt, response_format="json")
            decision = RoutingDecision(
                route=result.get("route", "chitchat"),
                intent=result.get("intent", "chitchat"),
                order_id=result.get("order_id"),
                product_sku=result.get("product_sku"),
                product_query=result.get("product_query"),
                product_field=result.get("product_field") or "info",
                action=result.get("action"),
                question=result.get("question"),
                knowledge_query=result.get("knowledge_query"),
                reason="LLM 路由",
                decided_by="llm",
            )
            return decision
        except Exception as e:
            logger.warning(f"LLM routing failed: {e}")
            return None

    # ========== 规则回退路由 ==========
    def _rule_route(self, text: str) -> RoutingDecision:
        """无 LLM 或 LLM 失败时的规则路由"""
        t = text.lower()
        order_ids = self.extract_order_ids(text)
        sku = self.extract_product_sku(text)

        # 政策/规则类（无具体订单号）优先走知识
        POLICY_HINTS = ("政策", "规则", "条件", "标准", "流程", "说明", "规定")
        if not order_ids and any(w in t for w in POLICY_HINTS):
            return RoutingDecision(
                route="knowledge", intent="knowledge",
                knowledge_query=text, reason="规则识别政策咨询", decided_by="rule",
            )

        # 业务动作
        if any(w in t for w in ("取消订单", "退掉订单", "不要了", "取消掉")):
            return RoutingDecision(
                route="business", intent="business_action", action="cancel_order",
                order_id=order_ids[0] if order_ids else None,
                reason="规则识别取消订单", decided_by="rule",
            )
        if any(w in t for w in ("申请退款", "我要退款", "发起退款")):
            return RoutingDecision(
                route="business", intent="business_action", action="apply_refund",
                order_id=order_ids[0] if order_ids else None,
                reason="规则识别申请退款", decided_by="rule",
            )

        # 订单查询
        if order_ids or any(w in t for w in ("我的订单", "订单号", "订单状态", "查订单", "订单在哪")):
            return RoutingDecision(
                route="business", intent="order_query",
                order_id=order_ids[0] if order_ids else None,
                reason="规则识别订单查询", decided_by="rule",
            )

        # 物流查询
        if any(w in t for w in ("物流", "快递", "发货", "到哪", "什么时候到", "配送", "签收")):
            return RoutingDecision(
                route="business", intent="shipping_query",
                order_id=order_ids[0] if order_ids else None,
                reason="规则识别物流查询", decided_by="rule",
            )

        # 退款资格（业务+知识）
        if any(w in t for w in ("能退吗", "可以退吗", "能不能退", "退货条件", "退款条件")):
            return RoutingDecision(
                route="hybrid", intent="refund_eligibility",
                order_id=order_ids[0] if order_ids else None,
                knowledge_query=text,
                reason="规则识别退款资格咨询", decided_by="rule",
            )

        # 退款查询
        if any(w in t for w in ("退款", "退货", "退钱")):
            return RoutingDecision(
                route="business", intent="refund_query",
                order_id=order_ids[0] if order_ids else None,
                reason="规则识别退款查询", decided_by="rule",
            )

        # 商品/库存/价格
        if sku or any(w in t for w in ("库存", "有货", "多少钱", "价格", "商品", "推荐")):
            field = "inventory" if any(w in t for w in ("库存", "有货")) else \
                    "price" if any(w in t for w in ("多少钱", "价格")) else "info"
            return RoutingDecision(
                route="business", intent="product_query",
                product_sku=sku, product_query=text, product_field=field,
                reason="规则识别商品查询", decided_by="rule",
            )

        # 政策/规则类 → 知识
        if any(w in t for w in POLICY_WORDS) or any(w in t for w in ("政策", "规则", "发票", "运费", "包邮", "保修")):
            return RoutingDecision(
                route="knowledge", intent="knowledge",
                knowledge_query=text, reason="规则识别知识咨询", decided_by="rule",
            )

        # 闲聊
        return RoutingDecision(
            route="chitchat", intent="chitchat",
            reason="默认闲聊", decided_by="rule",
        )

    # ========== 主入口 ==========
    async def decide(self, text: str, context: dict = None) -> RoutingDecision:
        """路由决策主流程"""
        # 1. 确定性守卫
        guard = self._guard(text)
        if guard:
            self._stats[guard.route] = self._stats.get(guard.route, 0) + 1
            return guard

        # 2. 模型路由（可选）
        decision = await self._llm_route(text, context) if self.use_llm else None

        # 3. 校验；失败则规则路由
        if decision is None or not decision.validate():
            if decision is not None:
                logger.warning(f"Invalid routing decision: route={decision.route} intent={decision.intent}")
            decision = self._rule_route(text)

        # 4. 规范化：白名单动作校验
        if decision.action and decision.action not in ALLOWED_ACTIONS:
            logger.warning(f"Action not allowlisted: {decision.action}")
            decision.action = None
            if decision.intent == "business_action":
                decision.intent = "order_query"
                decision.route = "business"

        # 5. 补全槽位（正则兜底）
        if not decision.order_id:
            ids = self.extract_order_ids(text)
            if ids:
                decision.order_id = ids[0]
        if not decision.product_sku:
            decision.product_sku = self.extract_product_sku(text)

        # 6. 业务动作缺订单号 → 澄清
        if decision.intent == "business_action" and not decision.order_id:
            decision.route = "clarify"
            decision.intent = "clarify"
            decision.question = "请问您要操作的是哪个订单呢？麻烦提供一下订单号。"

        self._stats[decision.route] = self._stats.get(decision.route, 0) + 1
        return decision

    def get_stats(self) -> dict:
        """路由统计"""
        total = sum(self._stats.values())
        return {
            "total": total,
            "distribution": dict(self._stats),
            "percentages": {
                k: round(v / total * 100, 1) if total else 0
                for k, v in self._stats.items()
            },
        }

    @staticmethod
    def get_route_rules() -> dict:
        """返回路由规则说明（供前端展示）"""
        return {
            "routes": {
                "business": {"name": "业务查询", "desc": "查询订单/物流/退款/商品/库存等业务数据",
                             "intents": sorted(ROUTE_INTENTS["business"])},
                "knowledge": {"name": "知识问答", "desc": "查询政策/规则/流程/说明等知识库内容",
                              "intents": sorted(ROUTE_INTENTS["knowledge"])},
                "hybrid": {"name": "混合处理", "desc": "同时需要业务数据与知识库（如退款资格判断）",
                           "intents": sorted(ROUTE_INTENTS["hybrid"])},
                "clarify": {"name": "澄清追问", "desc": "信息不足，先向用户追问",
                            "intents": sorted(ROUTE_INTENTS["clarify"])},
                "human": {"name": "人工介入", "desc": "转人工客服处理",
                          "intents": sorted(ROUTE_INTENTS["human"])},
                "chitchat": {"name": "闲聊", "desc": "问候/感谢/闲聊",
                             "intents": sorted(ROUTE_INTENTS["chitchat"])},
            },
            "allowed_actions": sorted(ALLOWED_ACTIONS),
            "guards": [
                {"name": "歧义指代", "desc": "出现「有个订单」等指代但无订单号 → 澄清",
                 "words": list(AMBIGUOUS_ORDER_WORDS)},
                {"name": "明确人工", "desc": "出现「转人工」等词 → 直接转人工",
                 "words": list(HUMAN_WORDS)},
                {"name": "通用地址", "desc": "通用退货/收货地址咨询 → 知识（非个人订单地址）"},
            ],
        }
