"""
数据库初始化脚本
- 创建所有表
- 导入内置知识库
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models.database import DatabaseManager, Base


# 数据库连接 URL
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://cs_user:cs_pass_2024@localhost:5432/cs_agent"
)


async def init_database():
    """初始化数据库"""
    print(f"Connecting to: {DATABASE_URL}")
    
    db = DatabaseManager(DATABASE_URL)
    
    # 创建表
    print("Creating tables...")
    await db.create_tables()
    print("Tables created successfully!")
    
    # 导入内置知识库
    print("Importing built-in knowledge base...")
    from src.modules.knowledge_base import KnowledgeBase
    
    kb = KnowledgeBase(
        db_session_factory=db.async_session_factory,
        mode="postgres"
    )
    await kb.init_from_builtin()
    print("Knowledge base imported!")
    
    # 关闭连接
    await db.close()
    print("Database initialization complete!")


async def reset_database():
    """重置数据库（删除所有表并重建）"""
    confirm = input("⚠️  This will DELETE ALL DATA. Type 'yes' to confirm: ")
    if confirm != "yes":
        print("Cancelled.")
        return
    
    db = DatabaseManager(DATABASE_URL)
    
    print("Dropping all tables...")
    await db.drop_tables()
    print("Tables dropped!")
    
    print("Recreating tables...")
    await db.create_tables()
    print("Tables recreated!")
    
    await db.close()
    print("Database reset complete!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        asyncio.run(reset_database())
    else:
        asyncio.run(init_database())
