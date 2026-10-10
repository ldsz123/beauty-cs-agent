"""
三级流水线单元测试
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.layers.emotion_layer import EmotionRecognitionLayer, EmotionType, EmotionIntensity
from src.layers.semantic_layer import SemanticClassificationLayer, IntentType, UrgencyLevel
from src.layers.entity_layer import EntityExtractionLayer


class TestEmotionLayer:
    """情感识别层测试"""
    
    def setup_method(self):
        self.layer = EmotionRecognitionLayer(llm_client=None)
    
    def test_angry_emotion(self):
        result = self.layer._rule_based_analysis("你们这是什么垃圾产品，太差了！")
        assert result.emotion == EmotionType.ANGRY
        assert result.confidence > 0
        assert len(result.triggers) > 0
    
    def test_anxious_emotion(self):
        result = self.layer._rule_based_analysis("我的订单怎么还没发货？什么时候能到？")
        assert result.emotion == EmotionType.ANXIOUS
    
    def test_urgent_emotion(self):
        result = self.layer._rule_based_analysis("紧急！今天必须送到，我等着用！")
        assert result.emotion in [EmotionType.URGENT, EmotionType.ANXIOUS]
    
    def test_satisfied_emotion(self):
        result = self.layer._rule_based_analysis("质量不错，很满意，好评！")
        assert result.emotion == EmotionType.SATISFIED
    
    def test_neutral_emotion(self):
        result = self.layer._rule_based_analysis("你好")
        # 只有 neutral 有基础分 0.1，归一化后 confidence 可能为 1.0
        # 但 emotion 应该是 neutral
        assert result.emotion == EmotionType.NEUTRAL
    
    def test_extreme_emotion(self):
        result = self.layer._rule_based_analysis("气死我了，我要投诉到底！找315！")
        assert result.intensity == EmotionIntensity.EXTREME
        assert result.need_human == True
    
    def test_empty_message(self):
        result = self.layer._rule_based_analysis("")
        assert result.emotion == EmotionType.NEUTRAL


class TestSemanticLayer:
    """语义分类层测试"""
    
    def setup_method(self):
        self.layer = SemanticClassificationLayer(llm_client=None)
    
    def test_order_status_intent(self):
        result = self.layer._fallback_classify("帮我查一下订单状态", None)
        assert result.primary_intent == IntentType.ORDER_STATUS
    
    def test_shipping_intent(self):
        result = self.layer._fallback_classify("我的快递到哪了？物流信息", None)
        assert result.primary_intent == IntentType.SHIPPING_INQUIRY
    
    def test_return_intent(self):
        result = self.layer._fallback_classify("我要退货退款", None)
        assert result.primary_intent == IntentType.RETURN_REFUND
    
    def test_complaint_intent(self):
        result = self.layer._fallback_classify("我要投诉你们商家", None)
        assert result.primary_intent == IntentType.COMPLAINT
    
    def test_product_inquiry(self):
        result = self.layer._fallback_classify("这款商品有货吗？介绍一下", None)
        assert result.primary_intent == IntentType.PRODUCT_INQUIRY
    
    def test_escalate(self):
        result = self.layer._fallback_classify("找人工客服", None)
        assert result.primary_intent == IntentType.ESCALATE


class TestEntityLayer:
    """实体提取层测试"""
    
    def setup_method(self):
        self.layer = EntityExtractionLayer(llm_client=None)
    
    def test_phone_extraction(self):
        result = self.layer._regex_extract("我的手机号是13812345678")
        assert result.get("phone") == "13812345678"
    
    def test_order_id_extraction(self):
        result = self.layer._regex_extract("订单号TB20240101123456")
        assert result.get("order_id") is not None
    
    def test_amount_extraction(self):
        result = self.layer._regex_extract("价格是199.5元")
        assert result.get("amount") == 199.5
    
    def test_quantity_extraction(self):
        result = self.layer._regex_extract("买了3件商品")
        assert result.get("quantity") == 3
    
    def test_date_extraction(self):
        result = self.layer._regex_extract("昨天下的单")
        assert result.get("date") == "昨天"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
