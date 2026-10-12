"""
电商智能客服 Agent 核心引擎
编排三级处理流水线，实现深度理解
"""
import os
import time
from dataclasses import dataclass, field
from typing import Optional, AsyncGenerator
from loguru import logger

from .layers.emotion_layer import EmotionRecognitionLayer, EmotionResult, EmotionType, EmotionIntensity
from .layers.semantic_layer import SemanticClassificationLayer, SemanticResult, IntentType, UrgencyLevel
from .layers.entity_layer import EntityExtractionLayer, ExtractedEntities
from .modules.vision_module import ImageUnderstandingModule, ImageUnderstandingResult
from .modules.session_manager import SessionManager
from .modules.knowledge_base import KnowledgeBase
from .services.action_executor import BusinessActionExecutor
from .modules.beauty_knowledge import BeautyKnowledgeBase, BeautyContext
from .modules.promotion_handler import PromotionHandler
from .modules.operations_manager import OperationsManager
from .modules.metrics_dashboard import MetricsDashboard
from .modules.workflow_engine import WorkflowEngine
from .modules.channel_adapter import ChannelAdapter
from .modules.retrieval_engine import RetrievalEngine
from .modules.trace_recorder import TraceRecorder
from .modules.human_service import HumanServiceManager
from .modules.admin_service import AdminService
from .modules.kb_manager import KBManager


@dataclass
class AgentResponse:
    """Agent 最终响应"""
    reply: str = ""
    emotion_result: Optional[EmotionResult] = None
    semantic_result: Optional[SemanticResult] = None
    entities: Optional[ExtractedEntities] = None
    actions: list = field(default_factory=list)
    need_human: bool = False
    confidence: float = 0.0
    processing_time_ms: int = 0
    sources: list = field(default_factory=list)
    trace_id: str = ""


class CustomerServiceAgent:
    """
    电商智能客服 Agent
    三级处理流水线：情感识别 → 语义分类 → 实体提取
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # 初始化各层
        self.emotion_layer = EmotionRecognitionLayer(
            llm_client=config.get("llm_client"),
            emotion_lexicon_path=config.get("emotion_lexicon_path", "config/emotion_lexicon.json"),
            rule_weight=config.get("emotion_rule_weight", 0.3),
            llm_weight=config.get("emotion_llm_weight", 0.7),
        )
        
        self.semantic_layer = SemanticClassificationLayer(
            llm_client=config.get("llm_client"),
            intent_examples_path=config.get("intent_examples_path"),
        )
        
        self.entity_layer = EntityExtractionLayer(
            llm_client=config.get("llm_client"),
        )
        
        self.vision_module = ImageUnderstandingModule(
            vision_llm_client=config.get("vision_llm_client"),
        )
        
        # 业务执行器
        self.action_executor = BusinessActionExecutor(config)

        # 知识库（支持 PostgreSQL + Redis）
        self.knowledge_base = KnowledgeBase(
            config=config.get("kb_config", {}),
            db_session_factory=config.get("db_session_factory"),
            redis_cache=config.get("redis_cache"),
            mode=config.get("kb_mode", "builtin"),
        )

        # 会话管理（支持 PostgreSQL + Redis）
        self.session_manager = SessionManager(
            ttl=config.get("session_ttl", 3600),
            max_history=config.get("max_history", 20),
            db_session_factory=config.get("db_session_factory"),
            redis_cache=config.get("redis_cache"),
            mode=config.get("session_mode", "memory"),
        )

        # ========== 新增模块 ==========
        # 美妆知识库
        self.beauty_kb = BeautyKnowledgeBase()

        # 大促处理器
        self.promotion_handler = PromotionHandler(beauty_kb=self.beauty_kb)

        # 运营操作管理器
        self.operations_manager = OperationsManager(beauty_kb=self.beauty_kb)

        # 业务数据看板
        self.metrics_dashboard = MetricsDashboard()

        # 工作流引擎
        self.workflow_engine = WorkflowEngine()
        self.workflow_engine.build_default_workflows()

        # 多渠道适配器
        self.channel_adapter = ChannelAdapter()

        # 检索增强引擎（关键词 + 向量 + 重排）
        self.retrieval_engine = RetrievalEngine(
            self.knowledge_base,
            llm_client=config.get("llm_client"),
        )

        # 链路记录器（问题排查）
        self.trace_recorder = TraceRecorder()

        # 人工客服管理器
        self.human_service = HumanServiceManager()

        # 运营管理后台
        self.admin_service = AdminService(
            beauty_kb=self.beauty_kb,
            operations_manager=self.operations_manager,
        )

        # 知识库管理（切片/版本/回滚）
        self.kb_manager = KBManager(knowledge_base=self.knowledge_base)

        # 是否将情感+意图+实体三级分析合并为单次 LLM 调用（降低延迟）
        self.combined_analysis = (
            config.get("llm_client") is not None
            and os.environ.get("LLM_COMBINED_ANALYSIS", "true").lower() == "true"
        )
        
        logger.info(f"CustomerServiceAgent initialized "
                    f"(session_mode={config.get('session_mode', 'memory')}, "
                    f"kb_mode={config.get('kb_mode', 'builtin')})")
    
    async def process(self, user_message: str,
                      session_id: str,
                      image_data: bytes = None) -> AgentResponse:
        """
        主处理流程 — 三级流水线
        """
        start_time = time.time()

        # 获取会话
        session = await self.session_manager.get_session(session_id)

        # 开始链路记录
        trace_id = self.trace_recorder.start_trace(session_id, user_message)

        # 图片理解（如有）
        image_info = None
        if image_data:
            image_info_obj = await self.vision_module.understand(image_data, context=user_message)
            if image_info_obj:
                image_info = image_info_obj.__dict__

        # ========== 三级分析（合并模式：单次 LLM 调用 / 否则串行三级） ==========
        use_combined = self.combined_analysis and not image_data
        t0 = time.time()

        if use_combined:
            try:
                emotion_result, semantic_result, entities = await self._analyze_combined(
                    user_message, session
                )
                self.trace_recorder.record_node(
                    trace_id, "analysis_combined",
                    input_summary={"message": user_message[:100], "mode": "combined"},
                    output_summary={
                        "emotion": emotion_result.emotion.value,
                        "intensity": emotion_result.intensity.value,
                        "intent": semantic_result.primary_intent.value,
                        "urgency": semantic_result.urgency.value,
                        "order_id": entities.order_id,
                    },
                    duration_ms=int((time.time() - t0) * 1000),
                )
            except Exception as e:
                logger.warning(f"Combined analysis failed, falling back to 3-layer: {e}")
                use_combined = False

        if not use_combined:
            # ========== 第一级：情感识别 ==========
            t0 = time.time()
            emotion_result = await self.emotion_layer.analyze(
                user_message, conversation_history=session.history
            )
            self.trace_recorder.record_node(
                trace_id, "emotion",
                input_summary={"message": user_message[:100]},
                output_summary={
                    "emotion": emotion_result.emotion.value,
                    "intensity": emotion_result.intensity.value,
                    "confidence": round(emotion_result.confidence, 3),
                },
                duration_ms=int((time.time() - t0) * 1000),
            )

            # ========== 第二级：语义分类 ==========
            t0 = time.time()
            semantic_result = await self.semantic_layer.classify(
                user_message, emotion_result=emotion_result,
                conversation_context=session.context
            )
            self.trace_recorder.record_node(
                trace_id, "semantic",
                input_summary={"message": user_message[:100], "emotion": emotion_result.emotion.value},
                output_summary={
                    "intent": semantic_result.primary_intent.value,
                    "confidence": round(semantic_result.confidence, 3),
                    "urgency": semantic_result.urgency.value,
                },
                duration_ms=int((time.time() - t0) * 1000),
            )

            # ========== 第三级：实体提取 ==========
            t0 = time.time()
            entities = await self.entity_layer.extract(
                user_message, intent=semantic_result.primary_intent,
                image_info=image_info
            )
            self.trace_recorder.record_node(
                trace_id, "entity",
                input_summary={"message": user_message[:100], "has_image": image_data is not None},
                output_summary={
                    "order_id": entities.order_id,
                    "tracking_number": entities.tracking_number,
                    "phone": entities.phone,
                },
                duration_ms=int((time.time() - t0) * 1000),
            )

        logger.debug(f"Emotion={emotion_result.emotion.value} Intent={semantic_result.primary_intent.value} "
                     f"Entities(order_id={entities.order_id})")

        # ========== 业务动作执行 ==========
        t0 = time.time()
        actions = await self.action_executor.execute(
            intent=semantic_result.primary_intent,
            entities=entities,
            session=session.__dict__
        )
        self.trace_recorder.record_node(
            trace_id, "action",
            input_summary={"intent": semantic_result.primary_intent.value},
            output_summary={"actions": actions},
            duration_ms=int((time.time() - t0) * 1000),
        )
        for act in actions:
            self.trace_recorder.record_business_query(
                trace_id, act.get("action", "unknown"), act
            )

        # ========== 知识检索（混合：关键词 + 向量 + 重排） ==========
        t0 = time.time()
        retrieval = await self.retrieval_engine.retrieve(
            query=user_message,
            intent=semantic_result.primary_intent,
            entities=entities,
        )
        kb_context = retrieval.to_context()
        sources = retrieval.to_sources()
        self.trace_recorder.record_node(
            trace_id, "retrieval",
            input_summary={"query": user_message[:100]},
            output_summary={
                "strategy": retrieval.strategy,
                "candidates": retrieval.total_candidates,
                "returned": len(retrieval.chunks),
            },
            duration_ms=int((time.time() - t0) * 1000),
        )
        self.trace_recorder.record_retrieval(trace_id, retrieval)

        # ========== 美妆知识库检索 ==========
        beauty_context = self._get_beauty_context(user_message, entities)
        beauty_recommendations = []
        if beauty_context:
            beauty_recommendations = self.beauty_kb.get_personalized_recommendations(beauty_context)

        # ========== 大促话术获取 ==========
        promotion_script = self._get_promotion_script(emotion_result, semantic_result)

        # ========== 生成回复 ==========
        reply = await self._generate_response(
            user_message=user_message,
            emotion=emotion_result,
            semantic=semantic_result,
            entities=entities,
            actions=actions,
            kb_context=kb_context,
            session=session,
            beauty_recommendations=beauty_recommendations,
            promotion_script=promotion_script,
        )
        
        # ========== 判断是否需要转人工 ==========
        need_human = self._check_escalation(emotion_result, semantic_result, session)

        # 转人工时创建工单
        if need_human:
            self.human_service.create_ticket(
                session_id=session_id,
                reason=semantic_result.primary_intent.value,
                category=self._infer_ticket_category(entities),
                user_message=user_message,
                emotion=emotion_result.emotion.value,
            )

        # 更新会话
        await self.session_manager.update_session(
            session_id,
            user_message,
            reply,
            emotion_result,
            semantic_result
        )
        
        processing_time = int((time.time() - start_time) * 1000)

        # ========== 记录业务指标 ==========
        self.metrics_dashboard.record_session({
            "session_id": session_id,
            "intent": semantic_result.primary_intent.value,
            "emotion": emotion_result.emotion.value,
            "resolved": not need_human,
            "need_human": need_human,
            "processing_time_ms": processing_time,
        })
        self.metrics_dashboard.record_issue(
            category=semantic_result.primary_intent.value,
            resolved=not need_human,
            ai_resolved=not need_human,
        )

        # ========== 结束链路记录 ==========
        self.trace_recorder.finish_trace(
            trace_id,
            reply=reply,
            intent=semantic_result.primary_intent.value,
            emotion=emotion_result.emotion.value,
            need_human=need_human,
            total_duration_ms=processing_time,
        )

        return AgentResponse(
            reply=reply,
            emotion_result=emotion_result,
            semantic_result=semantic_result,
            entities=entities,
            actions=actions,
            need_human=need_human,
            confidence=semantic_result.confidence,
            processing_time_ms=processing_time,
            sources=sources,
            trace_id=trace_id,
        )
    
    async def _analyze_combined(self, user_message, session):
        """
        单次 LLM 调用完成 情感 + 意图 + 实体 分析（降低延迟）
        失败时抛出异常，由调用方回退到三级流水线
        """
        prompt = f"""你是电商客服分析专家。请一次性分析用户消息，输出JSON。

用户消息：{user_message}

请分析三个维度：

1. 情感（emotion）：
   - type: angry(愤怒)/anxious(焦虑)/dissatisfied(不满)/neutral(中性)/satisfied(满意)/urgent(紧急)/grateful(感激)
   - intensity: 1-4（4最强）
   - confidence: 0-1

2. 意图（intent）：
   - primary: product_inquiry(商品咨询)/price_inquiry(价格)/promotion_inquiry(促销)/comparison(对比)/order_status(订单查询)/order_modify(订单修改)/payment_issue(支付问题)/shipping_inquiry(物流查询)/return_refund(退货退款)/exchange(换货)/complaint(投诉)/warranty(保修)/account_issue(账户问题)/tech_support(技术支持)/general_chat(闲聊)/escalate(转人工)
   - confidence: 0-1
   - urgency: low/medium/high/critical

3. 实体（entities）：order_id, tracking_number, product_name, phone, amount, quantity, issue_type（未找到填 null）

严格返回以下JSON格式（不要多余文字）：
{{"emotion":{{"type":"neutral","intensity":1,"confidence":0.8}},"intent":{{"primary":"general_chat","confidence":0.8,"urgency":"low"}},"entities":{{"order_id":null,"tracking_number":null,"product_name":null,"phone":null,"amount":null,"quantity":null,"issue_type":null}}}}"""

        result = await self.config["llm_client"].chat(prompt, response_format="json")

        # ---- 解析情感 ----
        emo = result.get("emotion", {}) or {}
        emo_type_str = emo.get("type", "neutral")
        try:
            emotion_type = EmotionType(emo_type_str)
        except ValueError:
            emotion_type = EmotionType.NEUTRAL
        try:
            intensity = EmotionIntensity(min(4, max(1, int(emo.get("intensity", 1)))))
        except (ValueError, TypeError):
            intensity = EmotionIntensity.LOW
        emotion_result = EmotionResult(
            emotion=emotion_type,
            intensity=intensity,
            confidence=float(emo.get("confidence", 0.6) or 0.6),
            triggers=[],
            need_human=(emotion_type == EmotionType.ANGRY and intensity.value >= 3),
        )

        # ---- 解析意图 ----
        it = result.get("intent", {}) or {}
        try:
            intent_type = IntentType(it.get("primary", "general_chat"))
        except ValueError:
            intent_type = IntentType.GENERAL_CHAT
        try:
            urgency = UrgencyLevel(it.get("urgency", "low"))
        except ValueError:
            urgency = UrgencyLevel.LOW
        semantic_result = SemanticResult(
            primary_intent=intent_type,
            confidence=float(it.get("confidence", 0.6) or 0.6),
            urgency=urgency,
        )
        # 情感影响紧急度
        semantic_result.urgency = self.semantic_layer._adjust_urgency(urgency, emotion_result)

        # ---- 解析实体（LLM + 正则合并） ----
        ent = result.get("entities", {}) or {}
        regex_entities = self.entity_layer._regex_extract(user_message)
        merged = {**{k: v for k, v in ent.items() if v}, **regex_entities}
        entities = ExtractedEntities(
            order_id=merged.get("order_id"),
            tracking_number=merged.get("tracking_number"),
            product_name=merged.get("product_name"),
            phone=merged.get("phone"),
            amount=merged.get("amount"),
            quantity=merged.get("quantity"),
            issue_type=merged.get("issue_type"),
            raw_entities=merged,
            confidence=min(0.95, 0.5 + 0.1 * len([v for v in merged.values() if v])),
        )

        return emotion_result, semantic_result, entities

    async def _generate_response(self, user_message, emotion, semantic,
                                  entities, actions, kb_context, session,
                                  beauty_recommendations=None,
                                  promotion_script=None) -> str:
        """生成最终回复"""
        
        # 根据情感调整语气
        tone_instruction = self._get_tone_instruction(emotion)

        # 构建上下文
        context_parts = []
        if kb_context:
            context_parts.append(f"知识库信息：{kb_context}")
        if actions:
            context_parts.append(f"已执行操作：{actions}")
        if entities.order_id:
            context_parts.append(f"订单号：{entities.order_id}")
        if beauty_recommendations:
            rec_text = "推荐商品：" + "、".join([p["name"] for p in beauty_recommendations[:3]])
            context_parts.append(rec_text)
        if promotion_script:
            context_parts.append(f"促销信息：{promotion_script}")

        context_str = "\n".join(context_parts)
        
        # 使用 LLM 生成回复
        if self.config.get("llm_client"):
            prompt = f"""你是电商客服助手。请根据以下信息生成专业、友好的回复。

{tone_instruction}

用户消息：{user_message}
意图：{semantic.primary_intent.value}
{context_str}

回复要求：
1. 先回应用户的情感状态（如道歉、安抚、感谢等）
2. 针对用户意图给出具体解决方案
3. 如需用户补充信息，清晰列出
4. 语气专业、友好、简洁
5. 中文回复，直接输出回复内容，不要输出思考过程或推理步骤"""
            
            try:
                reply = await self.config["llm_client"].chat(prompt)
                return reply
            except Exception as e:
                logger.error(f"LLM response generation failed: {e}")
        
        # Fallback 回复
        return self._fallback_response(emotion, semantic, entities, actions, kb_context)
    
    def _get_tone_instruction(self, emotion: EmotionResult) -> str:
        """根据情感生成语气指导"""
        tone_map = {
            EmotionType.ANGRY: "用户非常愤怒，请先真诚道歉，表达理解和重视，然后快速给出解决方案。语气要诚恳、耐心。",
            EmotionType.ANXIOUS: "用户感到焦虑，请先安抚情绪，表达会尽快处理，给出明确的时间承诺。",
            EmotionType.URGENT: "用户很着急，请优先处理，给出最快的解决方案和时间节点。",
            EmotionType.DISSATISFIED: "用户不满意，先承认不足，给出补偿或改进方案。",
            EmotionType.SATISFIED: "用户满意，感谢认可，保持友好。",
            EmotionType.GRATEFUL: "用户表示感谢，礼貌回应。",
            EmotionType.NEUTRAL: "正常客服语气，专业友好。",
        }
        return tone_map.get(emotion.emotion, "正常客服语气。")
    
    def _fallback_response(self, emotion, semantic, entities, actions,
                           kb_context: str = "") -> str:
        """无 LLM 时的 fallback 回复"""
        intent_reply_map = {
            IntentType.ORDER_STATUS: "我来帮您查询订单状态，请稍等。",
            IntentType.SHIPPING_INQUIRY: "我来为您查询物流信息。",
            IntentType.RETURN_REFUND: "我来帮您处理退货退款申请。",
            IntentType.EXCHANGE: "我来帮您处理换货申请。",
            IntentType.COMPLAINT: "您的投诉我已记录，专员会尽快联系您。",
            IntentType.WARRANTY: "商品质量问题可以申请售后，我来帮您处理。",
            IntentType.PRODUCT_INQUIRY: "我来为您查询商品信息。",
            IntentType.PRICE_INQUIRY: "我来为您查询价格信息。",
            IntentType.PAYMENT_ISSUE: "支付问题请检查网络或更换支付方式。",
            IntentType.PROMOTION_INQUIRY: "当前有新人首单减10元、满199减30等活动。",
            IntentType.ACCOUNT_ISSUE: "请描述您遇到的具体账户问题。",
            IntentType.ESCALATE: "正在为您转接人工客服，请稍候。",
            IntentType.GENERAL_CHAT: "您好，请问有什么可以帮您的？",
        }
        
        base_reply = intent_reply_map.get(semantic.primary_intent, "您好，请问有什么可以帮您的？")
        
        # 情感前缀（避免与回复内容重复道歉；闲聊意图不加前缀）
        if semantic.primary_intent != IntentType.GENERAL_CHAT:
            if emotion.emotion == EmotionType.ANGRY:
                if "抱歉" not in base_reply:
                    base_reply = "非常抱歉给您带来不好的体验！" + base_reply
            elif emotion.emotion == EmotionType.ANXIOUS:
                if "放心" not in base_reply:
                    base_reply = "请您放心，" + base_reply
        if emotion.emotion == EmotionType.GRATEFUL:
            base_reply = "不客气！" + base_reply
        
        # 附加知识库检索结果（爬取的电商知识）
        if kb_context:
            # 取第一条最相关知识，截断过长内容
            top_kb = kb_context.split("\n\n")[0]
            if len(top_kb) > 400:
                top_kb = top_kb[:400] + "……"
            base_reply = base_reply + "\n\n为您查到以下信息供参考：\n" + top_kb
        
        return base_reply
    
    def _get_beauty_context(self, user_message: str, entities) -> Optional[BeautyContext]:
        """从用户消息中提取美妆上下文"""
        # 检测肤质关键词
        skin_type_keywords = {
            "干性": "dry", "干皮": "dry", "干燥": "dry",
            "油性": "oily", "油皮": "oily", "出油": "oily",
            "混合": "combination", "混油": "combination", "混干": "combination",
            "敏感": "sensitive", "过敏": "sensitive",
            "中性": "normal",
        }
        skin_type = None
        for keyword, st in skin_type_keywords.items():
            if keyword in user_message:
                skin_type = st
                break

        # 检测护肤需求
        concern_keywords = {
            "美白": "美白", "提亮": "美白", "淡斑": "美白",
            "抗老": "抗衰老", "抗皱": "抗衰老", "细纹": "抗衰老",
            "保湿": "保湿", "补水": "保湿",
            "祛痘": "祛痘", "痘痘": "祛痘",
            "修复": "修复", "敏感肌": "修复",
        }
        concerns = []
        for keyword, concern in concern_keywords.items():
            if keyword in user_message:
                concerns.append(concern)

        if skin_type or concerns:
            return BeautyContext(
                skin_type=skin_type,
                skin_concerns=concerns,
            )
        return None

    def _get_promotion_script(self, emotion: EmotionResult, semantic: SemanticResult) -> Optional[str]:
        """获取大促话术"""
        # 根据意图确定场景
        scene_map = {
            IntentType.ORDER_STATUS: "发货",
            IntentType.SHIPPING_INQUIRY: "发货",
            IntentType.RETURN_REFUND: "售后",
            IntentType.COMPLAINT: "售后",
            IntentType.PRODUCT_INQUIRY: "开售",
            IntentType.PROMOTION_INQUIRY: "预热",
        }
        scene = scene_map.get(semantic.primary_intent)
        if scene:
            return self.promotion_handler.get_promotion_script(
                scene=scene,
                emotion_type=emotion.emotion.value,
            )
        return None

    def _infer_ticket_category(self, entities) -> str:
        """从实体推断工单分类（用于客服接待范围匹配）"""
        if entities.product_name:
            return "护肤"  # 简化：默认护肤，实际应按商品库查
        if entities.issue_type:
            return entities.issue_type
        return ""

    def _check_escalation(self, emotion: EmotionResult,
                          semantic: SemanticResult,
                          session) -> bool:
        """判断是否需要转人工"""
        # 愤怒且高强度
        if emotion.emotion == EmotionType.ANGRY and emotion.intensity.value >= 3:
            return True
        # 紧急
        if semantic.urgency == UrgencyLevel.CRITICAL:
            return True
        # 连续未解决
        if session.unresolved_count >= 3:
            return True
        # 用户要求人工
        if semantic.primary_intent == IntentType.ESCALATE:
            return True
        return False
