"""
美妆知识库模块测试
"""
import pytest
from src.modules.beauty_knowledge import BeautyKnowledgeBase, BeautyContext


class TestBeautyKnowledgeBase:
    """美妆知识库测试"""

    @pytest.fixture
    def kb(self):
        return BeautyKnowledgeBase()

    def test_get_skin_type_info(self, kb):
        """测试获取肤质信息"""
        info = kb.get_skin_type_info("dry")
        assert info is not None
        assert info["name"] == "干性肤质"

    def test_get_skin_type_info_not_found(self, kb):
        """测试获取不存在的肤质"""
        info = kb.get_skin_type_info("unknown")
        assert info is None

    def test_recommend_by_skin_type(self, kb):
        """测试根据肤质推荐产品"""
        results = kb.recommend_by_skin_type("dry")
        assert len(results) > 0
        assert all("dry" in p.get("suitable_skin_types", []) for p in results)

    def test_recommend_by_skin_type_with_category(self, kb):
        """测试根据肤质和品类推荐"""
        results = kb.recommend_by_skin_type("oily", "护肤")
        assert len(results) > 0
        assert all(p.get("category") == "护肤" for p in results)

    def test_search_ingredient(self, kb):
        """测试搜索成分"""
        results = kb.search_ingredient("玻尿酸")
        assert len(results) > 0
        assert any("玻尿酸" in r["name"] for r in results)

    def test_search_ingredient_not_found(self, kb):
        """测试搜索不存在的成分"""
        results = kb.search_ingredient("不存在的成分xyz")
        assert len(results) == 0

    def test_get_ingredient_details(self, kb):
        """测试获取成分详情"""
        details = kb.get_ingredient_details("ing_001")
        assert details is not None
        assert details["name"] == "玻尿酸"

    def test_recommend_ingredients_for_concern(self, kb):
        """测试根据护肤需求推荐成分"""
        results = kb.recommend_ingredients_for_concern("美白")
        assert len(results) > 0

    def test_search_products(self, kb):
        """测试搜索产品"""
        results = kb.search_products("精华")
        assert len(results) > 0

    def test_search_products_with_filters(self, kb):
        """测试带过滤器的产品搜索"""
        results = kb.search_products("精华", {"max_price": 1000})
        assert all(p["price"] <= 1000 for p in results)

    def test_get_product_details(self, kb):
        """测试获取产品详情"""
        product = kb.get_product_details("prod_001")
        assert product is not None
        assert product["name"] == "小棕瓶修护精华"

    def test_compare_products(self, kb):
        """测试产品对比"""
        result = kb.compare_products(["prod_001", "prod_002"])
        assert "products" in result
        assert "summary" in result
        assert len(result["products"]) == 2

    def test_get_promotion_script(self, kb):
        """测试获取大促话术"""
        script = kb.get_promotion_script("预热")
        assert script is not None
        assert len(script) > 0

    def test_get_promotion_script_with_emotion(self, kb):
        """测试获取带情感的大促话术"""
        script = kb.get_promotion_script("售后", "angry")
        assert script is not None

    def test_get_personalized_recommendations(self, kb):
        """测试个性化推荐"""
        context = BeautyContext(
            skin_type="dry",
            skin_concerns=["保湿", "抗衰老"],
        )
        results = kb.get_personalized_recommendations(context)
        assert len(results) > 0

    def test_get_personalized_recommendations_with_budget(self, kb):
        """测试带预算的个性化推荐"""
        context = BeautyContext(
            skin_type="oily",
            skin_concerns=["控油"],
            budget_range=(100, 500),
        )
        results = kb.get_personalized_recommendations(context)
        assert all(100 <= p["price"] <= 500 for p in results)
