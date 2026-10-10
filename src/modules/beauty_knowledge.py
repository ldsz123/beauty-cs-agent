"""
美妆知识库模块
肤质匹配、成分查询、产品推荐、使用建议
"""
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class BeautyContext:
    """美妆上下文"""
    skin_type: Optional[str] = None
    skin_concerns: list = field(default_factory=list)
    budget_range: Optional[tuple] = None  # (min, max)
    preferred_brands: list = field(default_factory=list)
    ingredients_to_avoid: list = field(default_factory=list)


class BeautyKnowledgeBase:
    """美妆知识库"""

    def __init__(self, data_dir: str = "data/knowledge_base"):
        self.data_dir = Path(data_dir)
        self.skin_types: dict = {}
        self.ingredients: dict = {}
        self.products: list = []
        self.promotion_scripts: list = []
        self._load_data()
        logger.info(f"BeautyKnowledgeBase initialized: {len(self.skin_types)} skin types, {len(self.ingredients)} ingredients, {len(self.products)} products")

    def _load_data(self):
        """加载知识库数据"""
        try:
            # 肤质类型
            skin_path = self.data_dir / "skin_types.json"
            if skin_path.exists():
                with open(skin_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.skin_types = {item["id"]: item for item in data}

            # 成分知识
            ing_path = self.data_dir / "ingredients.json"
            if ing_path.exists():
                with open(ing_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.ingredients = {item["id"]: item for item in data}

            # 产品库
            prod_path = self.data_dir / "products.json"
            if prod_path.exists():
                with open(prod_path, "r", encoding="utf-8") as f:
                    self.products = json.load(f)

            # 大促话术
            script_path = self.data_dir / "promotion_scripts.json"
            if script_path.exists():
                with open(script_path, "r", encoding="utf-8") as f:
                    self.promotion_scripts = json.load(f)

        except Exception as e:
            logger.error(f"Failed to load beauty KB: {e}")

    # ========== 肤质匹配 ==========
    def get_skin_type_info(self, skin_type_id: str) -> Optional[dict]:
        """获取肤质信息"""
        return self.skin_types.get(skin_type_id)

    def recommend_by_skin_type(self, skin_type_id: str, category: str = None) -> list:
        """根据肤质推荐产品"""
        recommendations = []
        for product in self.products:
            if skin_type_id in product.get("suitable_skin_types", []):
                if category is None or product.get("category") == category:
                    recommendations.append(product)
        return sorted(recommendations, key=lambda x: x.get("rating", 0), reverse=True)

    # ========== 成分查询 ==========
    def search_ingredient(self, query: str) -> list:
        """搜索成分"""
        results = []
        query_lower = query.lower()
        for ing_id, ing in self.ingredients.items():
            if query_lower in ing["name"].lower() or query_lower in ing.get("name_en", "").lower():
                results.append(ing)
        return results

    def get_ingredient_details(self, ingredient_id: str) -> Optional[dict]:
        """获取成分详情"""
        return self.ingredients.get(ingredient_id)

    def recommend_ingredients_for_concern(self, concern: str) -> list:
        """根据护肤需求推荐成分"""
        concern_map = {
            "美白": ["美白", "提亮肤色", "淡斑"],
            "抗衰老": ["抗皱", "抗衰老", "紧致"],
            "保湿": ["保湿", "锁水"],
            "祛痘": ["祛痘", "控油", "疏通毛孔"],
            "修复": ["修复", "舒缓", "屏障"],
            "防晒": ["防晒", "抗氧化"],
        }
        keywords = concern_map.get(concern, [concern])
        results = []
        for ing in self.ingredients.values():
            for kw in keywords:
                if any(kw in e for e in ing.get("efficacy", [])):
                    results.append(ing)
                    break
        return results

    # ========== 产品推荐 ==========
    def search_products(self, query: str, filters: dict = None) -> list:
        """搜索产品"""
        results = []
        query_lower = query.lower()

        for product in self.products:
            match = False
            # 名称匹配
            if query_lower in product.get("name", "").lower():
                match = True
            # 品牌匹配
            elif query_lower in product.get("brand", "").lower():
                match = True
            # 标签匹配
            elif any(query_lower in tag.lower() for tag in product.get("tags", [])):
                match = True
            # 成分匹配
            elif any(query_lower in ing.lower() for ing in product.get("ingredients", [])):
                match = True

            if match:
                # 应用过滤器
                if filters:
                    if "category" in filters and product.get("category") != filters["category"]:
                        continue
                    if "max_price" in filters and product.get("price", 0) > filters["max_price"]:
                        continue
                    if "brand" in filters and product.get("brand") != filters["brand"]:
                        continue
                results.append(product)

        return sorted(results, key=lambda x: x.get("sales_count", 0), reverse=True)

    def get_product_details(self, product_id: str) -> Optional[dict]:
        """获取产品详情"""
        for product in self.products:
            if product["id"] == product_id:
                return product
        return None

    def compare_products(self, product_ids: list) -> dict:
        """产品对比"""
        products = [self.get_product_details(pid) for pid in product_ids if self.get_product_details(pid)]
        if len(products) < 2:
            return {"error": "需要至少2个产品进行对比"}

        comparison = {
            "products": products,
            "summary": {
                "price_range": {
                    "min": min(p["price"] for p in products),
                    "max": max(p["price"] for p in products),
                },
                "common_ingredients": list(set(products[0].get("ingredients", [])) & set(products[1].get("ingredients", []))) if len(products) >= 2 else [],
                "rating_comparison": {p["name"]: p["rating"] for p in products},
            }
        }
        return comparison

    # ========== 大促话术 ==========
    def get_promotion_script(self, scene: str, emotion_type: str = None, variables: dict = None) -> Optional[str]:
        """获取大促话术"""
        # 优先匹配情感+场景
        if emotion_type:
            for script in self.promotion_scripts:
                if script.get("scene") == scene and script.get("emotion_type") == emotion_type:
                    return self._render_script(script, variables or {})

        # 其次匹配场景
        for script in self.promotion_scripts:
            if script.get("scene") == scene and not script.get("emotion_type"):
                return self._render_script(script, variables or {})

        return None

    def _render_script(self, script: dict, variables: dict) -> str:
        """渲染话术模板"""
        template = script["template"]
        for var in script.get("variables", []):
            value = variables.get(var, f"[{var}]")
            template = template.replace(f"{{{var}}}", str(value))
        return template

    # ========== 智能推荐 ==========
    def get_personalized_recommendations(self, context: BeautyContext, top_k: int = 5) -> list:
        """个性化推荐"""
        scored_products = []

        for product in self.products:
            score = 0.0

            # 肤质匹配（权重最高）
            if context.skin_type and context.skin_type in product.get("suitable_skin_types", []):
                score += 3.0

            # 护肤需求匹配
            for concern in context.skin_concerns:
                concern_ingredients = self.recommend_ingredients_for_concern(concern)
                concern_ing_ids = {i["id"] for i in concern_ingredients}
                product_ingredients = set(product.get("ingredients", []))
                # 检查产品成分是否匹配需求
                for ing_name in product_ingredients:
                    for ci in concern_ingredients:
                        if ing_name in ci["name"] or ci["name"] in ing_name:
                            score += 2.0
                            break

            # 预算匹配（硬性过滤 + 加分）
            if context.budget_range:
                min_price, max_price = context.budget_range
                product_price = product.get("price", 0)
                if min_price <= product_price <= max_price:
                    score += 1.5
                else:
                    continue  # 超出预算直接跳过

            # 品牌偏好
            if context.preferred_brands and product.get("brand") in context.preferred_brands:
                score += 1.0

            # 避免成分
            if context.ingredients_to_avoid:
                if any(avoid in ing for ing in product.get("ingredients", []) for avoid in context.ingredients_to_avoid):
                    score -= 5.0

            # 销量和评分加成
            score += product.get("rating", 5.0) * 0.1
            score += min(product.get("sales_count", 0) / 10000, 1.0) * 0.5

            if score > 0:
                scored_products.append((score, product))

        scored_products.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored_products[:top_k]]
