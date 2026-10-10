"""
图理解模块
支持用户发送的图片理解（商品截图/物流截图/聊天记录/凭证等）
"""
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


@dataclass
class ImageUnderstandingResult:
    """图片理解结果"""
    description: str = ""
    image_type: str = "unknown"
    extracted_text: str = ""
    relevant_info: dict = field(default_factory=dict)
    confidence: float = 0.0


class ImageUnderstandingModule:
    """
    图理解模块
    使用多模态 LLM 理解图片内容
    """
    
    def __init__(self, vision_llm_client=None):
        self.vision_llm = vision_llm_client
        logger.info("ImageUnderstandingModule initialized")
    
    async def understand(self, image_data: bytes,
                         context: str = "") -> Optional[ImageUnderstandingResult]:
        """图片理解"""
        if not self.vision_llm:
            logger.warning("No vision LLM client available")
            return None
        
        try:
            prompt = f"""你是电商客服图片理解专家。请分析这张图片。

上下文：{context}

请分析：
1. 图片类型：商品截图/物流截图/聊天记录/支付凭证/商品问题照片/其他
2. 图片内容详细描述
3. 图片中可见的所有文字信息
4. 与用户问题相关的关键信息（订单号、商品名、金额等）

JSON格式返回：
{{"image_type": "类型", "description": "详细描述", "extracted_text": "图片中文字", "relevant_info": {{"key": "value"}}, "confidence": 0.0-1.0}}"""
            
            result = await self.vision_llm.chat_with_image(
                prompt, image_data, response_format="json"
            )
            
            return ImageUnderstandingResult(
                description=result.get("description", ""),
                image_type=result.get("image_type", "unknown"),
                extracted_text=result.get("extracted_text", ""),
                relevant_info=result.get("relevant_info", {}),
                confidence=result.get("confidence", 0.0)
            )
        except Exception as e:
            logger.error(f"Image understanding failed: {e}")
            return None
