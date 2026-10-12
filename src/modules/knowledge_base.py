"""
知识库模块 — RAG 检索
支持：内置数据（默认）/ PostgreSQL 持久化 + Redis 缓存
"""
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class SearchResult:
    """搜索结果"""
    content: str
    score: float
    category: str = ""
    metadata: dict = field(default_factory=dict)


class KnowledgeBase:
    """
    电商知识库
    支持三种模式：
    1. builtin — 内置静态数据（默认）
    2. postgres — PostgreSQL 持久化
    3. redis — Redis 缓存 + PostgreSQL
    """
    
    def __init__(self, config: dict = None,
                 db_session_factory=None,
                 redis_cache=None,
                 mode: str = "builtin"):
        self.config = config or {}
        self.mode = mode
        self.top_k = self.config.get("top_k", 5)
        self.cache_ttl = self.config.get("cache_ttl", 300)
        self._db_factory = db_session_factory
        self._redis = redis_cache
        
        # 内置知识库
        self._builtin_kb = self._load_builtin_kb()
        
        logger.info(f"KnowledgeBase initialized (mode={mode}, builtin_entries={len(self._builtin_kb)})")
    
    def _load_builtin_kb(self) -> list[dict]:
        """加载内置知识库（优先加载爬取导入的数据）"""
        # 优先加载爬虫导入的数据
        imported_path = Path("data/knowledge_base/imported_kb.json")
        if imported_path.exists():
            try:
                with open(imported_path, "r", encoding="utf-8") as f:
                    imported = json.load(f)
                if imported:
                    logger.info(f"Loaded {len(imported)} entries from imported KB")
                    return imported
            except Exception as e:
                logger.warning(f"Failed to load imported KB: {e}")
        
        return self._get_default_kb()
    
    def _get_default_kb(self) -> list[dict]:
        """默认知识库（爬取数据不存在时的 fallback）"""
        return [
            {
                "category": "退货政策",
                "content": "商品自签收之日起7天内可无理由退货，需保持商品完好、包装齐全。定制商品、生鲜食品不支持无理由退货。",
                "tags": ["退货", "退款", "7天无理由"]
            },
            {
                "category": "物流说明",
                "content": "订单确认后48小时内发货，一般3-5天送达。偏远地区可能延长至7天。如遇物流异常请联系客服。",
                "tags": ["物流", "快递", "发货", "配送"]
            },
            {
                "category": "支付方式",
                "content": "支持支付宝、微信支付、银行卡支付。如支付失败请检查网络或更换支付方式重试。",
                "tags": ["支付", "付款", "支付宝", "微信"]
            },
            {
                "category": "售后服务",
                "content": "商品质量问题15天内可退换货，1年内保修。请保留好商品和包装以便处理售后。",
                "tags": ["售后", "保修", "质量问题", "换货"]
            },
            {
                "category": "优惠活动",
                "content": "新用户首单立减10元。满199减30，满299减50。会员享额外95折优惠。",
                "tags": ["优惠", "活动", "满减", "折扣"]
            },
            {
                "category": "订单修改",
                "content": "订单发货前可修改地址/手机号，发货后无法修改。请在下单后30分钟内完成修改。",
                "tags": ["修改", "地址", "订单修改"]
            },
            {
                "category": "发票说明",
                "content": "支持开具电子发票和专用发票。电子发票在订单完成后发送至您的邮箱，专用发票需提供开票信息。",
                "tags": ["发票", "开票"]
            },
        ]
    
    async def search(self, query: str,
                     intent=None,
                     entities=None,
                     top_k: int = None) -> str:
        """知识库检索"""
        top_k = top_k or self.top_k
        
        # Redis 缓存
        if self.mode == "redis" and self._redis and self._redis.is_available:
            cached = await self._redis.get_cached_kb(query)
            if cached:
                return cached
        
        # PostgreSQL 模式
        if self.mode in ("postgres", "redis") and self._db_factory:
            result = await self._search_postgres(query, intent, entities, top_k)
            if result:
                # 写入缓存
                if self.mode == "redis" and self._redis and self._redis.is_available:
                    await self._redis.cache_kb_result(query, result, self.cache_ttl)
                return result
        
        # 内置模式（关键词匹配）
        result = self._search_builtin(query, intent, top_k)
        
        # 缓存内置结果
        if self.mode == "redis" and self._redis and self._redis.is_available:
            await self._redis.cache_kb_result(query, result, self.cache_ttl)
        
        return result
    
    def _search_builtin(self, query: str, intent, top_k: int) -> str:
        """内置检索（jieba 分词 + 关键词加权匹配）"""
        # 提取查询关键词
        query_keywords = self._extract_keywords(query)
        
        results = []
        for entry in self._builtin_kb:
            score = 0.0
            content = entry.get("content", "")
            tags = entry.get("tags", [])
            title = entry.get("title", "")
            
            # 标签匹配（权重最高）
            for tag in tags:
                if tag in query:
                    score += 2.0
            
            # 关键词与内容/标题匹配
            for kw in query_keywords:
                if kw in title:
                    score += 1.5
                if kw in content:
                    score += 1.0
            
            # 原始查询整串匹配（短语匹配加分）
            query_short = query.replace("？", "").replace("?", "").strip()
            if len(query_short) >= 4 and query_short in title:
                score += 3.0
            
            # 意图匹配（单次加分，避免多标签重复累加）
            if intent:
                intent_category_map = {
                    "return_refund": ["退货", "退款"],
                    "shipping_inquiry": ["物流", "快递", "配送", "运费", "包邮"],
                    "payment_issue": ["支付", "付款"],
                    "exchange": ["换货"],
                    "warranty": ["保修", "售后"],
                    "order_status": ["订单", "发货"],
                    "order_modify": ["修改订单", "地址"],
                    "account_issue": ["账户", "密码", "登录"],
                }
                related_tags = intent_category_map.get(intent.value, [])
                if any(tag in content or tag in tags for tag in related_tags):
                    score += 3.0
            
            if score > 0:
                results.append(SearchResult(
                    content=content,
                    score=score,
                    category=entry.get("category", ""),
                    metadata={"tags": tags, "title": title}
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        results = results[:top_k]
        
        if not results:
            return ""
        
        return "\n\n".join([f"[{r.category}] {r.content}" for r in results])
    
    @staticmethod
    def _extract_keywords(query: str) -> list[str]:
        """jieba 提取查询关键词"""
        try:
            import jieba.analyse
            keywords = jieba.analyse.extract_tags(query, topK=8)
            return [kw for kw in keywords if len(kw) >= 2]
        except ImportError:
            # fallback：手动切分常见电商词
            ecommerce_terms = [
                "退货", "退款", "换货", "物流", "快递", "发货", "配送",
                "支付", "付款", "发票", "保修", "售后", "会员", "优惠",
                "订单", "商品", "地址", "账户", "密码", "运费", "签收",
            ]
            return [t for t in ecommerce_terms if t in query]
    
    async def _search_postgres(self, query: str, intent, entities, top_k: int) -> Optional[str]:
        """PostgreSQL 全文检索"""
        try:
            from src.models.database import KnowledgeEntry
            from sqlalchemy import select, or_, func
            
            async with self._db_factory() as db:
                # 构建查询条件
                keywords = [w for w in query if len(w) > 1]
                
                # 简单：用 LIKE 匹配标签和内容
                conditions = []
                for kw in keywords:
                    conditions.append(KnowledgeEntry.content.contains(kw))
                    conditions.append(func.cast(KnowledgeEntry.tags, db.String).contains(kw))
                
                if intent:
                    conditions.append(KnowledgeEntry.category.contains(intent.value))
                
                stmt = (
                    select(KnowledgeEntry)
                    .where(KnowledgeEntry.is_active == True)
                    .where(or_(*conditions) if conditions else True)
                    .order_by(KnowledgeEntry.priority.desc())
                    .limit(top_k)
                )
                
                result = await db.execute(stmt)
                entries = result.scalars().all()
                
                if not entries:
                    return None
                
                return "\n\n".join([
                    f"[{e.category}] {e.content}"
                    for e in entries
                ])
        except Exception as e:
            logger.error(f"PostgreSQL KB search failed: {e}")
            return None
    
    def get_all_chunks(self) -> list[dict]:
        """获取所有知识切片（供检索/向量化使用）"""
        chunks = []
        for idx, entry in enumerate(self._builtin_kb):
            content = entry.get("content", "")
            chunks.append({
                "chunk_id": entry.get("id") or f"kb_{idx:04d}",
                "content": content,
                "title": entry.get("title", content[:30]),
                "category": entry.get("category", ""),
                "tags": entry.get("tags", []),
            })
        return chunks

    async def add_entry(self, category: str, content: str,
                        tags: list = None, priority: int = 0):
        """添加知识库条目"""
        # 内置模式
        if self.mode == "builtin":
            self._builtin_kb.append({
                "category": category,
                "content": content,
                "tags": tags or [],
            })
            return
        
        # PostgreSQL 模式
        if self._db_factory:
            try:
                from src.models.database import KnowledgeEntry
                async with self._db_factory() as db:
                    entry = KnowledgeEntry(
                        category=category,
                        title=content[:50],
                        content=content,
                        tags=tags or [],
                        priority=priority,
                    )
                    db.add(entry)
                    await db.commit()
                    logger.info(f"KB entry added: {category}")
            except Exception as e:
                logger.error(f"Failed to add KB entry: {e}")
    
    async def init_from_builtin(self):
        """将内置数据导入 PostgreSQL"""
        if not self._db_factory:
            logger.warning("No DB factory, cannot import builtin KB")
            return
        
        try:
            from src.models.database import KnowledgeEntry
            async with self._db_factory() as db:
                # 检查是否已导入
                from sqlalchemy import select, func
                stmt = select(func.count(KnowledgeEntry.id))
                result = await db.execute(stmt)
                count = result.scalar()
                
                if count > 0:
                    logger.info(f"KB already has {count} entries, skipping import")
                    return
                
                # 导入内置数据
                for entry in self._builtin_kb:
                    kb_entry = KnowledgeEntry(
                        category=entry["category"],
                        title=entry["content"][:50],
                        content=entry["content"],
                        tags=entry.get("tags", []),
                        priority=0,
                    )
                    db.add(kb_entry)
                
                await db.commit()
                logger.info(f"Imported {len(self._builtin_kb)} builtin KB entries")
        except Exception as e:
            logger.error(f"Failed to import builtin KB: {e}")
