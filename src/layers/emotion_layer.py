"""
情感识别层 — 第一级处理
基于规则引擎 + LLM 双路识别，融合输出
"""
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
import json
from pathlib import Path
from loguru import logger


class EmotionType(Enum):
    """电商场景情感分类"""
    ANGRY = "angry"           # 愤怒
    ANXIOUS = "anxious"       # 焦虑
    DISSATISFIED = "dissatisfied"  # 不满
    NEUTRAL = "neutral"       # 中性
    SATISFIED = "satisfied"   # 满意
    URGENT = "urgent"         # 紧急
    GRATEFUL = "grateful"     # 感激


class EmotionIntensity(Enum):
    """情感强度"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    EXTREME = 4


@dataclass
class EmotionResult:
    emotion: EmotionType = EmotionType.NEUTRAL
    intensity: EmotionIntensity = EmotionIntensity.LOW
    confidence: float = 0.0
    triggers: list = field(default_factory=list)
    raw_score: dict = field(default_factory=dict)
    need_human: bool = False


class EmotionRecognitionLayer:
    """
    情感识别层
    - 规则引擎：关键词匹配（快速低延迟）
    - LLM 推理：上下文理解（语义级准确）
    - 双路融合输出
    """
    
    def __init__(self, llm_client=None, 
                 emotion_lexicon_path: str = "config/emotion_lexicon.json",
                 rule_weight: float = 0.3,
                 llm_weight: float = 0.7):
        self.llm = llm_client
        self.rule_weight = rule_weight
        self.llm_weight = llm_weight
        
        # 加载情感词典
        self.emotion_keywords = self._load_emotion_lexicon(emotion_lexicon_path)
        
        # 默认关键词（词典加载失败时的 fallback）
        if not self.emotion_keywords:
            self.emotion_keywords = {
                "angry": ["垃圾", "骗子", "投诉", "差评", "退款", "坑人", "太差",
                          "骗钱", "虚假宣传", "态度恶劣", "再也不买", "坑爹", "黑心",
                          "无耻", "恶劣", "气死", "愤怒"],
                "anxious": ["怎么还没", "什么时候", "急", "担心", "会不会",
                           "能不能", "怎么办", "来不及", "快点", "多久", "等到",
                           "焦虑", "不安"],
                "dissatisfied": ["不满意", "不太行", "一般般", "凑合", "勉强",
                                "不如", "没有想象中", "差强人意", "失望", "后悔"],
                "urgent": ["紧急", "加急", "马上", "立刻", "今天必须",
                          "等不及", "着急", "赶时间", "越快越好", "火速"],
                "satisfied": ["不错", "满意", "好评", "喜欢", "推荐", "物超所值",
                             "质量好", "速度快", "很棒", "给力", "赞", "五星"],
                "grateful": ["谢谢", "感谢", "辛苦", "麻烦了", "多谢", "感激"],
            }
        
        logger.info("EmotionRecognitionLayer initialized")
    
    def _load_emotion_lexicon(self, path: str) -> dict:
        """加载情感词典"""
        try:
            lexicon_path = Path(path)
            if lexicon_path.exists():
                with open(lexicon_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("emotions", {})
        except Exception as e:
            logger.warning(f"Failed to load emotion lexicon: {e}")
        return {}
    
    async def analyze(self, user_message: str,
                      conversation_history: list = None) -> EmotionResult:
        """双路情感识别"""
        # 规则引擎
        rule_result = self._rule_based_analysis(user_message)
        
        # LLM 分析
        llm_result = await self._llm_analysis(user_message, conversation_history)
        
        # 融合
        return self._fuse_results(rule_result, llm_result)
    
    def _rule_based_analysis(self, message: str) -> EmotionResult:
        """基于关键词的规则匹配"""
        scores = {emotion: 0.0 for emotion in EmotionType}
        scores[EmotionType.NEUTRAL] = 0.1  # 基础中性分
        triggers = []
        
        for emotion_name, keywords in self.emotion_keywords.items():
            try:
                emotion_type = EmotionType(emotion_name)
            except ValueError:
                continue
            
            if isinstance(keywords, dict):
                # 带权重的格式
                kw_list = keywords.get("keywords", [])
                weight = keywords.get("weight", 1.0)
            elif isinstance(keywords, list):
                kw_list = keywords
                weight = 1.0
            else:
                continue
            
            for keyword in kw_list:
                if keyword in message:
                    scores[emotion_type] += weight
                    triggers.append(keyword)
        
        # 归一化
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}
        
        max_emotion = max(scores, key=scores.get)
        max_score = scores[max_emotion]
        
        # 强度映射
        if max_score > 0.6:
            intensity = EmotionIntensity.HIGH
        elif max_score > 0.3:
            intensity = EmotionIntensity.MEDIUM
        else:
            intensity = EmotionIntensity.LOW
        
        # 检查是否有极端情感
        has_extreme = any(kw in message for kw in ["气死我了", "投诉到底", "工商", "315", "消协"])
        if has_extreme:
            intensity = EmotionIntensity.EXTREME
        
        return EmotionResult(
            emotion=max_emotion,
            intensity=intensity,
            confidence=max_score,
            triggers=triggers,
            raw_score={e.value: round(s, 3) for e, s in scores.items()},
            need_human=(max_emotion == EmotionType.ANGRY and intensity.value >= 3)
        )
    
    async def _llm_analysis(self, message: str,
                            history: list = None) -> EmotionResult:
        """基于 LLM 的情感分析"""
        if not self.llm:
            return EmotionResult(
                emotion=EmotionType.NEUTRAL,
                intensity=EmotionIntensity.LOW,
                confidence=0.0,
                triggers=[],
                raw_score={}
            )
        
        try:
            history_str = ""
            if history:
                recent = history[-3:]  # 取最近3轮
                history_str = "\n".join([
                    f"{'用户' if m.get('role') == 'user' else '客服'}: {m.get('content', '')}"
                    for m in recent
                ])
            
            prompt = f"""你是电商客服情感分析专家。请分析用户消息的情感状态。

用户消息：{message}
{'对话历史：' + history_str if history_str else ''}

请从以下维度分析：
1. 主要情感类型：愤怒/焦虑/不满/中性/满意/紧急/感激
2. 情感强度：1-4级（4最强烈）
3. 触发情感的关键短语
4. 是否需要人工介入

以JSON格式返回：
{{"emotion": "情感类型", "intensity": 1-4, "confidence": 0-1, "triggers": ["短语"], "need_human": true/false}}"""
            
            result = await self.llm.chat(prompt, response_format="json")
            
            emotion_map = {
                "愤怒": "angry", "焦虑": "anxious", "不满": "dissatisfied",
                "中性": "neutral", "满意": "satisfied", "紧急": "urgent",
                "感激": "grateful"
            }
            emotion_en = emotion_map.get(result.get("emotion", ""), result.get("emotion", "neutral"))
            
            return EmotionResult(
                emotion=EmotionType(emotion_en) if emotion_en in [e.value for e in EmotionType] else EmotionType.NEUTRAL,
                intensity=EmotionIntensity(min(4, max(1, result.get("intensity", 1)))),
                confidence=result.get("confidence", 0.5),
                triggers=result.get("triggers", []),
                raw_score={},
                need_human=result.get("need_human", False)
            )
        except Exception as e:
            logger.error(f"LLM emotion analysis failed: {e}")
            return EmotionResult(confidence=0.0)
    
    def _fuse_results(self, rule_result: EmotionResult,
                      llm_result: EmotionResult) -> EmotionResult:
        """融合两路结果"""
        # LLM 不可用时，直接用规则结果
        if llm_result.confidence == 0:
            return rule_result
        
        # 一致时提升置信度
        if rule_result.emotion == llm_result.emotion:
            confidence = min(0.95,
                           rule_result.confidence * self.rule_weight +
                           llm_result.confidence * self.llm_weight)
            return EmotionResult(
                emotion=llm_result.emotion,
                intensity=llm_result.intensity,
                confidence=confidence,
                triggers=list(set(rule_result.triggers + llm_result.triggers)),
                raw_score=rule_result.raw_score,
                need_human=rule_result.need_human or llm_result.need_human
            )
        else:
            # 不一致时以 LLM 为主
            return llm_result
