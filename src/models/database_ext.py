"""
扩展数据库模型 — 美妆电商全链路
新增：美妆知识库、运营数据、大促管理、工作流、多渠道接入
"""
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text,
    DateTime, ForeignKey, JSON, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


# ========== 美妆产品库 ==========
class Product(Base):
    """美妆产品表"""
    __tablename__ = "products"

    id = Column(String(64), primary_key=True, comment="商品ID")
    name = Column(String(256), nullable=False, comment="商品名称")
    brand = Column(String(128), nullable=False, comment="品牌")
    category = Column(String(64), nullable=False, comment="品类：护肤/彩妆/香水/个护")
    subcategory = Column(String(64), nullable=True, comment="子品类：精华/面霜/口红等")
    price = Column(Float, nullable=False, comment="当前价格")
    original_price = Column(Float, nullable=True, comment="原价")
    description = Column(Text, nullable=True, comment="商品描述")
    ingredients = Column(JSON, default=list, comment="成分列表")
    suitable_skin_types = Column(JSON, default=list, comment="适合肤质")
    usage = Column(Text, nullable=True, comment="使用方法")
    specifications = Column(JSON, default=dict, comment="规格信息")
    stock = Column(Integer, default=0, comment="库存")
    sales_count = Column(Integer, default=0, comment="销量")
    rating = Column(Float, default=5.0, comment="评分")
    tags = Column(JSON, default=list, comment="标签")
    images = Column(JSON, default=list, comment="图片URL列表")
    status = Column(String(20), default="active", comment="状态：active/inactive")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_products_category", "category"),
        Index("idx_products_brand", "brand"),
        Index("idx_products_status", "status"),
    )


# ========== 肤质类型 ==========
class SkinType(Base):
    """肤质类型表"""
    __tablename__ = "skin_types"

    id = Column(String(32), primary_key=True, comment="肤质ID")
    name = Column(String(64), nullable=False, comment="肤质名称")
    description = Column(Text, nullable=True, comment="肤质描述")
    characteristics = Column(JSON, default=list, comment="特征")
    recommendations = Column(JSON, default=list, comment="护理建议")
    common_issues = Column(JSON, default=list, comment="常见问题")


# ========== 成分知识库 ==========
class IngredientKnowledge(Base):
    """成分知识库"""
    __tablename__ = "ingredient_knowledge"

    id = Column(String(64), primary_key=True, comment="成分ID")
    name = Column(String(128), nullable=False, comment="成分名称")
    name_en = Column(String(128), nullable=True, comment="英文名称")
    category = Column(String(64), nullable=False, comment="类别：保湿/美白/抗衰老/祛痘/防晒")
    efficacy = Column(JSON, default=list, comment="功效")
    suitable_skin_types = Column(JSON, default=list, comment="适合肤质")
    unsuitable_skin_types = Column(JSON, default=list, comment="不适合肤质")
    safety_level = Column(Integer, default=3, comment="安全等级1-5")
    description = Column(Text, nullable=True, comment="详细描述")
    related_products = Column(JSON, default=list, comment="相关产品ID")

    __table_args__ = (
        Index("idx_ingredient_category", "category"),
    )


# ========== 大促活动 ==========
class Promotion(Base):
    """大促活动表"""
    __tablename__ = "promotions"

    id = Column(String(64), primary_key=True, comment="活动ID")
    name = Column(String(256), nullable=False, comment="活动名称")
    promotion_type = Column(String(32), nullable=False, comment="类型：预售/满减/秒杀/拼团/优惠券")
    start_time = Column(DateTime, nullable=False, comment="开始时间")
    end_time = Column(DateTime, nullable=False, comment="结束时间")
    rules = Column(JSON, default=dict, comment="活动规则")
    applicable_products = Column(JSON, default=list, comment="适用商品ID列表")
    applicable_categories = Column(JSON, default=list, comment="适用品类列表")
    discount_info = Column(JSON, default=dict, comment="折扣信息")
    stock_limit = Column(Integer, nullable=True, comment="库存限制")
    per_user_limit = Column(Integer, nullable=True, comment="每人限购")
    status = Column(String(20), default="pending", comment="状态：pending/active/ended")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_promotions_status", "status"),
        Index("idx_promotions_time", "start_time", "end_time"),
    )


# ========== 运营数据（GMV/转化/成本） ==========
class OperationMetrics(Base):
    """运营指标表 — 按天聚合"""
    __tablename__ = "operation_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, comment="日期")
    channel = Column(String(64), default="all", comment="渠道：all/web/app/feishu")

    # GMV 指标
    total_gmv = Column(Float, default=0.0, comment="总GMV")
    order_count = Column(Integer, default=0, comment="订单数")
    avg_order_value = Column(Float, default=0.0, comment="客单价")

    # 转化指标
    uv = Column(Integer, default=0, comment="独立访客数")
    pv = Column(Integer, default=0, comment="页面浏览量")
    consultation_count = Column(Integer, default=0, comment="咨询数")
    conversion_rate = Column(Float, default=0.0, comment="转化率")
    cart_rate = Column(Float, default=0.0, comment="加购率")
    checkout_rate = Column(Float, default=0.0, comment="结算率")

    # AI 服务指标
    ai_session_count = Column(Integer, default=0, comment="AI会话数")
    ai_resolved_count = Column(Integer, default=0, comment="AI解决数")
    ai_resolution_rate = Column(Float, default=0.0, comment="AI解决率")
    ai_avg_response_time = Column(Float, default=0.0, comment="AI平均响应时间(ms)")
    human_escalation_count = Column(Integer, default=0, comment="转人工数")
    human_escalation_rate = Column(Float, default=0.0, comment="转人工率")

    # 成本指标
    llm_cost = Column(Float, default=0.0, comment="LLM调用成本")
    human_service_cost = Column(Float, default=0.0, comment="人工客服成本")
    cost_per_order = Column(Float, default=0.0, comment="单订单服务成本")

    # 满意度
    satisfaction_score = Column(Float, default=0.0, comment="平均满意度")
    feedback_count = Column(Integer, default=0, comment="反馈数")

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_metrics_date", "date"),
        Index("idx_metrics_channel", "channel"),
        UniqueConstraint("date", "channel", name="uq_date_channel"),
    )


# ========== 问题分类统计 ==========
class IssueCategory(Base):
    """问题分类统计表"""
    __tablename__ = "issue_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, comment="日期")
    category = Column(String(64), nullable=False, comment="问题大类")
    subcategory = Column(String(64), nullable=True, comment="问题小类")
    count = Column(Integer, default=0, comment="数量")
    ai_resolved = Column(Integer, default=0, comment="AI解决数")
    human_resolved = Column(Integer, default=0, comment="人工解决数")
    avg_resolution_time = Column(Float, default=0.0, comment="平均解决时间(分钟)")
    satisfaction_avg = Column(Float, default=0.0, comment="平均满意度")

    __table_args__ = (
        Index("idx_issue_cat_date", "date"),
        Index("idx_issue_cat_category", "category"),
    )


# ========== 工作流定义 ==========
class WorkflowDefinition(Base):
    """工作流定义表"""
    __tablename__ = "workflow_definitions"

    id = Column(String(64), primary_key=True, comment="工作流ID")
    name = Column(String(256), nullable=False, comment="工作流名称")
    description = Column(Text, nullable=True, comment="描述")
    trigger_type = Column(String(32), nullable=False, comment="触发类型：intent/event/webhook")
    trigger_config = Column(JSON, default=dict, comment="触发条件配置")
    nodes = Column(JSON, default=list, comment="节点定义")
    edges = Column(JSON, default=list, comment="边定义")
    variables = Column(JSON, default=dict, comment="变量定义")
    status = Column(String(20), default="draft", comment="状态：draft/published/archived")
    version = Column(Integer, default=1, comment="版本号")
    created_by = Column(String(64), nullable=True, comment="创建者")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_workflow_status", "status"),
    )


# ========== 工作流执行记录 ==========
class WorkflowExecution(Base):
    """工作流执行记录"""
    __tablename__ = "workflow_executions"

    id = Column(String(64), primary_key=True, comment="执行ID")
    workflow_id = Column(String(64), ForeignKey("workflow_definitions.id"), nullable=False)
    session_id = Column(String(64), nullable=True, comment="关联会话ID")
    trigger_data = Column(JSON, default=dict, comment="触发数据")
    current_node = Column(String(64), nullable=True, comment="当前节点")
    variables = Column(JSON, default=dict, comment="执行变量")
    status = Column(String(20), default="running", comment="状态：running/completed/failed/cancelled")
    result = Column(JSON, nullable=True, comment="执行结果")
    error_message = Column(Text, nullable=True, comment="错误信息")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True, comment="完成时间")

    __table_args__ = (
        Index("idx_workflow_exec_status", "status"),
        Index("idx_workflow_exec_session", "session_id"),
    )


# ========== 多渠道接入配置 ==========
class ChannelConfig(Base):
    """多渠道接入配置"""
    __tablename__ = "channel_configs"

    id = Column(String(64), primary_key=True, comment="渠道ID")
    channel_type = Column(String(32), nullable=False, comment="渠道类型：web/feishu/wechat/api")
    name = Column(String(128), nullable=False, comment="渠道名称")
    config = Column(JSON, default=dict, comment="渠道配置")
    webhook_url = Column(String(512), nullable=True, comment="Webhook URL")
    api_key = Column(String(256), nullable=True, comment="API Key")
    is_active = Column(Boolean, default=True, comment="是否启用")
    priority = Column(Integer, default=0, comment="优先级")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_channel_type", "channel_type"),
        Index("idx_channel_active", "is_active"),
    )


# ========== 客户画像 ==========
class CustomerProfile(Base):
    """客户画像表"""
    __tablename__ = "customer_profiles"

    user_id = Column(String(64), primary_key=True, comment="用户ID")
    nickname = Column(String(128), nullable=True, comment="昵称")
    skin_type = Column(String(32), nullable=True, comment="肤质")
    skin_concerns = Column(JSON, default=list, comment="护肤关注点")
    purchase_history = Column(JSON, default=list, comment="购买历史")
    preference_tags = Column(JSON, default=list, comment="偏好标签")
    total_orders = Column(Integer, default=0, comment="总订单数")
    total_spent = Column(Float, default=0.0, comment="总消费金额")
    avg_order_value = Column(Float, default=0.0, comment="客单价")
    satisfaction_history = Column(JSON, default=list, comment="满意度历史")
    tags = Column(JSON, default=list, comment="标签：VIP/新客/流失风险等")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_customer_skin_type", "skin_type"),
    )


# ========== 大促话术模板 ==========
class PromotionScript(Base):
    """大促话术模板"""
    __tablename__ = "promotion_scripts"

    id = Column(String(64), primary_key=True, comment="话术ID")
    promotion_id = Column(String(64), ForeignKey("promotions.id"), nullable=True, comment="关联活动")
    scene = Column(String(64), nullable=False, comment="场景：预热/开售/催付/发货/售后")
    emotion_type = Column(String(32), nullable=True, comment="适用情感类型")
    template = Column(Text, nullable=False, comment="话术模板")
    variables = Column(JSON, default=list, comment="变量列表")
    priority = Column(Integer, default=0, comment="优先级")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_script_scene", "scene"),
        Index("idx_script_active", "is_active"),
    )
