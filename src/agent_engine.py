"""
电商智能客服 Agent 核心引擎
编排三级处理流水线，实现深度理解
"""
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
        
        # ========== 第一级：情感识别 ==========
        emotion_result = await self.emotion_layer.analyze(
            user_message,
            conversation_history=session.history
        )
        logger.debug(f"Emotion: {emotion_result.emotion.value} (intensity={emotion_result.intensity.value})")
        
        # ========== 第二级：语义分类 ==========
        semantic_result = await self.semantic_layer.classify(
            user_message,
            emotion_result=emotion_result,
            conversation_context=session.context
        )
        logger.debug(f"Intent: {semantic_result.primary_intent.value} (confidence={semantic_result.confidence:.2f})")
        
        # ========== 第三级：实体提取 ==========
        image_info = None
        if image_data:
            image_info_obj = await self.vision_module.understand(image_data, context=user_message)
            if image_info_obj:
                image_info = image_info_obj.__dict__
        
        entities = await self.entity_layer.extract(
            user_message,
            intent=semantic_result.primary_intent,
            image_info=image_info
        )
        logger.debug(f"Entities: order_id={entities.order_id}, product={entities.product_name}")
        
        # ========== 业务动作执行 ==========
        actions = await self.action_executor.execute(
            intent=semantic_result.primary_intent,
            entities=entities,
            session=session.__dict__
        )
        
        # ========== 知识库检索 ==========
        kb_context = await self.knowledge_base.search(
            query=user_message,
            intent=semantic_result.primary_intent,
            entities=entities
        )

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

        return AgentResponse(
            reply=reply,
            emotion_result=emotion_result,
            semantic_result=semantic_result,
            entities=entities,
            actions=actions,
            need_human=need_human,
            confidence=semantic_result.confidence,
            processing_time_ms=processing_time
        )
    
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
5. 中文回复，直接输出回复内容"""
            
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
