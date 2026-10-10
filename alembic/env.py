"""
Alembic 环境配置
用于数据库迁移管理
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 导入所有模型（确保迁移能检测到所有表）
from src.models.database import Base
from src.models.database import SessionRecord, ConversationRecord
from src.models.database import KnowledgeEntry, UserRecord
from src.models.database import EscalationRecord, OperationLog

# Alembic 配置对象
config = context.config

# 从 alembic.ini 加载日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标 metadata（用于自动生成迁移）
target_metadata = Base.metadata

# 从环境变量获取数据库 URL
def get_database_url():
    """获取数据库连接 URL"""
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    # 默认本地开发配置
    return "postgresql+asyncpg://cs_user:cs_pass_2024@localhost:5432/cs_agent"


def run_migrations_offline() -> None:
    """离线迁移模式（生成 SQL 脚本，不实际执行）"""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # 比较列类型变化
        compare_server_default=True,  # 比较默认值变化
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线迁移模式（直接执行到数据库）"""
    # 将数据库 URL 注入到配置中
    config.set_main_option("sqlalchemy.url", get_database_url())
    
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
