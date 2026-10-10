"""
初始数据库 Schema
创建所有核心表

Revision ID: 000001
Revises: 
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "000001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ====== 会话表 ======
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(64), primary_key=True, comment="会话ID"),
        sa.Column("user_id", sa.String(64), nullable=True, comment="用户ID"),
        sa.Column("status", sa.String(20), server_default="active", comment="会话状态"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), comment="更新时间"),
        sa.Column("ended_at", sa.DateTime, nullable=True, comment="结束时间"),
        sa.Column("emotion_history", sa.JSON, server_default="[]", comment="情感变化历史"),
        sa.Column("context", sa.JSON, server_default="{}", comment="会话上下文"),
        sa.Column("unresolved_count", sa.Integer, server_default="0", comment="连续未解决次数"),
        sa.Column("metadata", sa.JSON, server_default="{}", comment="扩展元数据"),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_status", "sessions", ["status"])
    op.create_index("idx_sessions_updated_at", "sessions", ["updated_at"])

    # ====== 对话记录表 ======
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, comment="角色"),
        sa.Column("content", sa.Text, nullable=False, comment="消息内容"),
        sa.Column("timestamp", sa.DateTime, server_default=sa.func.now()),
        sa.Column("emotion_type", sa.String(20), nullable=True),
        sa.Column("emotion_intensity", sa.Integer, nullable=True),
        sa.Column("intent", sa.String(40), nullable=True),
        sa.Column("entities", sa.JSON, nullable=True),
        sa.Column("actions", sa.JSON, nullable=True),
        sa.Column("need_human", sa.Boolean, server_default="false"),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("processing_time_ms", sa.Integer, nullable=True),
    )
    op.create_index("idx_conversations_session_id", "conversations", ["session_id"])
    op.create_index("idx_conversations_timestamp", "conversations", ["timestamp"])

    # ====== 知识库表 ======
    op.create_table(
        "knowledge_base",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(64), nullable=False, comment="分类"),
        sa.Column("title", sa.String(256), nullable=False, comment="标题"),
        sa.Column("content", sa.Text, nullable=False, comment="内容"),
        sa.Column("tags", sa.JSON, server_default="[]", comment="标签"),
        sa.Column("embedding", sa.JSON, nullable=True, comment="向量嵌入"),
        sa.Column("is_active", sa.Boolean, server_default="true", comment="是否启用"),
        sa.Column("priority", sa.Integer, server_default="0", comment="优先级"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_kb_category", "knowledge_base", ["category"])
    op.create_index("idx_kb_is_active", "knowledge_base", ["is_active"])

    # ====== 用户表 ======
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True, comment="用户ID"),
        sa.Column("nickname", sa.String(64), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("level", sa.String(20), server_default="normal"),
        sa.Column("total_sessions", sa.Integer, server_default="0"),
        sa.Column("satisfaction_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("last_active_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_users_phone", "users", ["phone"], unique=True)

    # ====== 转人工记录表 ======
    op.create_table(
        "escalations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("sessions.id")),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("emotion_type", sa.String(20), nullable=True),
        sa.Column("emotion_intensity", sa.Integer, nullable=True),
        sa.Column("resolved", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
    )
    op.create_index("idx_escalations_session_id", "escalations", ["session_id"])
    op.create_index("idx_escalations_created_at", "escalations", ["created_at"])

    # ====== 操作日志表 ======
    op.create_table(
        "operation_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(128), nullable=True),
        sa.Column("result", sa.String(20), nullable=True),
        sa.Column("detail", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_logs_session_id", "operation_logs", ["session_id"])
    op.create_index("idx_logs_action", "operation_logs", ["action"])
    op.create_index("idx_logs_created_at", "operation_logs", ["created_at"])


def downgrade() -> None:
    # 按依赖顺序删除
    op.drop_index("idx_logs_created_at", table_name="operation_logs")
    op.drop_index("idx_logs_action", table_name="operation_logs")
    op.drop_index("idx_logs_session_id", table_name="operation_logs")
    op.drop_table("operation_logs")

    op.drop_index("idx_escalations_created_at", table_name="escalations")
    op.drop_index("idx_escalations_session_id", table_name="escalations")
    op.drop_table("escalations")

    op.drop_index("idx_users_phone", table_name="users")
    op.drop_table("users")

    op.drop_index("idx_kb_is_active", table_name="knowledge_base")
    op.drop_index("idx_kb_category", table_name="knowledge_base")
    op.drop_table("knowledge_base")

    op.drop_index("idx_conversations_timestamp", table_name="conversations")
    op.drop_index("idx_conversations_session_id", table_name="conversations")
    op.drop_table("conversations")

    op.drop_index("idx_sessions_updated_at", table_name="sessions")
    op.create_index("idx_sessions_status", table_name="sessions")
    op.drop_index("idx_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
