"""
实体提取层 — 第三级处理
基于正则 + LLM 双路提取，支持业务实体识别
"""
import re
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


@dataclass
class ExtractedEntities:
    """提取的实体集合"""
    order_id: Optional[str] = None
    tracking_number: Optional[str] = None
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    product_category: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    user_id: Optional[str] = None
    amount: Optional[float] = None
    quantity: Optional[int] = None
    time_reference: Optional[str] = None
    date: Optional[str] = None
    issue_type: Optional[str] = None
    issue_description: Optional[str] = None
    has_image: bool = False
    image_description: Optional[str] = None
    raw_entities: dict = field(default_factory=dict)
    confidence: float = 0.0


class EntityExtractionLayer:
    """实体提取层"""
    
    def __init__(self, llm_client=None):
        self.llm = llm_client
        
        # 正则规则
        self.patterns = {
            "order_id": [
                r"订单[号编号]?[：:\s]*([A-Za-z0-9]{10,20})",
                r"([A-Z]{2}\d{12,18})",
                r"(?<!\d)(\d{16,20})(?!\d)",
            ],
            "phone": [
                r"(?<!\d)(1[3-9]\d{9})(?!\d)",
            ],
            "tracking_number": [
                r"物流[号单]?[：:\s]*([A-Za-z0-9]{10,25})",
                r"([A-Z]{2}\d{9}[A-Z]{2})",
            ],
            "amount": [
                r"[￥¥$]?(\d+\.?\d*)\s*元?",
            ],
            "quantity": [
                r"(\d+)\s*(个|件|份|台|瓶|盒|只)",
            ],
            "date": [
                r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})",
                r"(昨天|今天|前天|上周|上个月)",
            ],
        }
        
        logger.info("EntityExtractionLayer initialized")
    
    async def extract(self, user_message: str,
                      intent=None,
                      image_info: dict = None) -> ExtractedEntities:
        """实体提取主流程"""
        # 1. 正则提取
        regex_result = self._regex_extract(user_message)
        
        # 2. LLM 语义提取
        llm_result = await self._llm_extract(user_message, intent)
        
        # 3. 合并
        merged = self._merge_results(regex_result, llm_result)
        
        # 4. 图片信息
        if image_info:
            merged.has_image = True
            merged.image_description = image_info.get("description")
            # 图片中的文字可能包含订单号等
            if image_info.get("extracted_text"):
                img_regex = self._regex_extract(image_info["extracted_text"])
                for k, v in img_regex.items():
                    if not getattr(merged, k):
                        setattr(merged, k, v)
        
        return merged
    
    def _regex_extract(self, message: str) -> dict:
        """正则精确提取"""
        results = {}
        for entity_type, patterns in self.patterns.items():
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    if entity_type == "amount":
                        try:
                            results[entity_type] = float(value)
                        except ValueError:
                            pass
                    elif entity_type == "quantity":
                        try:
                            results[entity_type] = int(value)
                        except ValueError:
                            pass
                    else:
                        results[entity_type] = value
                    break
        return results
    
    async def _llm_extract(self, message: str, intent=None) -> dict:
        """LLM 语义提取"""
        if not self.llm:
            return {}
        
        try:
            intent_hint = f"当前意图：{intent.value}" if intent else ""
            prompt = f"""你是电商客服实体提取专家。请从用户消息中提取业务实体。

用户消息：{message}
{intent_hint}

提取字段：order_id(订单号), tracking_number(物流单号), product_name(商品名称), 
product_sku(SKU), phone(手机号), address(地址), amount(金额数字), 
quantity(数量数字), time_reference(时间引用), issue_type(问题类型), 
issue_description(问题描述)

JSON格式返回，未找到返回null。"""
            
            result = await self.llm.chat(prompt, response_format="json")
            return result
        except Exception as e:
            logger.error(f"LLM entity extraction failed: {e}")
            return {}
    
    def _merge_results(self, regex_result: dict, llm_result: dict) -> ExtractedEntities:
        """合并结果"""
        merged = {**llm_result}
        # 正则结果补充 LLM 未提取到的字段
        for k, v in regex_result.items():
            if k not in merged or merged[k] is None:
                merged[k] = v
        
        return ExtractedEntities(
            order_id=merged.get("order_id"),
            tracking_number=merged.get("tracking_number"),
            product_name=merged.get("product_name"),
            product_sku=merged.get("product_sku"),
            product_category=merged.get("product_category"),
            phone=merged.get("phone"),
            address=merged.get("address"),
            amount=merged.get("amount"),
            quantity=merged.get("quantity"),
            time_reference=merged.get("time_reference"),
            date=merged.get("date"),
            issue_type=merged.get("issue_type"),
            issue_description=merged.get("issue_description"),
            raw_entities=merged,
            confidence=min(0.95, 0.5 + 0.1 * len([v for v in merged.values() if v]))
        )
