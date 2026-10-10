"""
数据库管理脚本
集成 Alembic 迁移 + 数据初始化 + 备份恢复

用法：
    python scripts/manage_db.py init          # 初始化（建表 + 导入数据）
    python scripts/manage_db.py migrate       # 执行待执行的迁移
    python scripts/manage_db.py revision      # 生成新的迁移脚本
    python scripts/manage_db.py downgrade     # 回滚最后一次迁移
    python scripts/manage_db.py history       # 查看迁移历史
    python scripts/manage_db.py reset         # 重置数据库（危险！）
    python scripts/manage_db.py seed          # 填充示例数据
    python scripts/manage_db.py status        # 查看数据库状态
    python scripts/manage_db.py backup        # 备份数据库
"""
import asyncio
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://cs_user:cs_pass_2024@localhost:5432/cs_agent"
)

SYNC_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://cs_user:cs_pass_2024@localhost:5432/cs_agent"
).replace("postgresql+asyncpg", "postgresql+psycopg2")


def run_alembic_command(args: list[str]):
    """执行 Alembic 命令"""
    cmd = ["alembic"] + args
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env)
    return result.returncode == 0


async def init_database():
    """完整初始化：建表 + 导入知识库 + 填充示例数据"""
    print("=" * 60)
    print("  Database Initialization")
    print("=" * 60)
    
    # 步骤 1: 执行迁移（建表）
    print("\n[1/4] Running migrations (creating tables)...")
    if not run_alembic_command(["upgrade", "head"]):
        print("❌ Migration failed!")
        return False
    print("✅ Tables created")
    
    # 步骤 2: 导入知识库
    print("\n[2/4] Importing knowledge base...")
    from src.models.database import DatabaseManager
    from src.modules.knowledge_base import KnowledgeBase
    
    db = DatabaseManager(DATABASE_URL)
    kb = KnowledgeBase(
        db_session_factory=db.async_session_factory,
        mode="postgres"
    )
    await kb.init_from_builtin()
    print("✅ Knowledge base imported")
    
    # 步骤 3: 填充示例数据
    print("\n[3/4] Seeding sample data...")
    await seed_sample_data(db)
    print("✅ Sample data seeded")
    
    # 步骤 4: 验证
    print("\n[4/4] Verifying...")
    await verify_database(db)
    
    await db.close()
    
    print("\n" + "=" * 60)
    print("  ✅ Database initialization complete!")
    print("=" * 60)
    return True


async def seed_sample_data(db: "DatabaseManager"):
    """填充示例数据"""
    from src.models.database import KnowledgeEntry, UserRecord
    
    async with db.async_session_factory() as session:
        # 检查是否已有数据
        from sqlalchemy import select, func
        stmt = select(func.count(KnowledgeEntry.id))
        result = await session.execute(stmt)
        if result.scalar() > 0:
            print("  Knowledge base already has data, skipping...")
        else:
            # 导入更多示例知识库
            sample_kb = [
                {"category": "会员权益", "content": "普通会员享95折，银卡会员享9折，金卡会员享85折。累计消费满1000升银卡，满5000升金卡。", 
                 "tags": ["会员", "等级", "折扣"]},
                {"category": "商品保障", "content": "所有商品正品保证，假一赔十。支持7天无理由退换，15天质量问题退换。", 
                 "tags": ["正品", "保障", "假货"]},
                {"category": "配送范围", "content": "支持全国配送（含港澳台）。偏远地区可能额外收取运费，结算时自动显示。", 
                 "tags": ["配送", "范围", "港澳台", "偏远地区"]},
            ]
            for item in sample_kb:
                entry = KnowledgeEntry(
                    category=item["category"],
                    title=item["content"][:50],
                    content=item["content"],
                    tags=item["tags"],
                    priority=0,
                )
                session.add(entry)
            await session.commit()
        
        # 添加示例用户
        stmt = select(func.count(UserRecord.id))
        result = await session.execute(stmt)
        if result.scalar() == 0:
            sample_users = [
                UserRecord(id="user_001", nickname="张三", phone="13800138001", level="gold"),
                UserRecord(id="user_002", nickname="李四", phone="13800138002", level="silver"),
                UserRecord(id="user_003", nickname="王五", phone="13800138003", level="normal"),
            ]
            for user in sample_users:
                session.add(user)
            await session.commit()
            print(f"  Added {len(sample_users)} sample users")


async def verify_database(db: "DatabaseManager"):
    """验证数据库状态"""
    from src.models.database import (
        SessionRecord, ConversationRecord, KnowledgeEntry,
        UserRecord, EscalationRecord, OperationLog
    )
    from sqlalchemy import select, func
    
    async with db.async_session_factory() as session:
        tables = [
            ("sessions", SessionRecord),
            ("conversations", ConversationRecord),
            ("knowledge_base", KnowledgeEntry),
            ("users", UserRecord),
            ("escalations", EscalationRecord),
            ("operation_logs", OperationLog),
        ]
        
        for name, model in tables:
            stmt = select(func.count(model.id))
            result = await session.execute(stmt)
            count = result.scalar()
            print(f"  {name}: {count} rows")


async def backup_database():
    """备份数据库（使用 pg_dump）"""
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"cs_agent_backup_{timestamp}.sql"
    
    # 从 DATABASE_URL 解析连接信息
    import re
    match = re.match(r"postgresql\+psycopg2://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", SYNC_DATABASE_URL)
    if not match:
        print(f"❌ Cannot parse DATABASE_URL: {SYNC_DATABASE_URL}")
        return
    
    user, password, host, port, dbname = match.groups()
    
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    
    cmd = [
        "pg_dump",
        "-h", host,
        "-p", port,
        "-U", user,
        "-d", dbname,
        "-F", "plain",  # 纯文本格式
        "--encoding=UTF8",
        "-f", str(backup_file),
    ]
    
    print(f"Backing up to: {backup_file}")
    result = subprocess.run(cmd, env=env)
    
    if result.returncode == 0:
        print(f"✅ Backup saved: {backup_file}")
    else:
        print("❌ Backup failed! Make sure pg_dump is installed and accessible.")


def show_status():
    """显示数据库状态"""
    print("=" * 60)
    print("  Database Status")
    print("=" * 60)
    print(f"  DATABASE_URL: {DATABASE_URL}")
    print()
    
    # 当前迁移版本
    print("--- Migration Status ---")
    run_alembic_command(["current"])
    print()
    
    # 待执行迁移
    print("--- Pending Migrations ---")
    run_alembic_command(["history", "--indicate-current"])
    print()


def show_history():
    """显示迁移历史"""
    run_alembic_command(["history", "--verbose"])


def create_revision():
    """创建新的迁移脚本"""
    message = input("Migration message (e.g., 'add_product_table'): ").strip()
    if not message:
        print("❌ Message required")
        return
    
    # 自动生成迁移（基于模型变化）
    run_alembic_command(["revision", "--autogenerate", "-m", message])


def run_migration():
    """执行迁移"""
    run_alembic_command(["upgrade", "head"])


def run_downgrade():
    """回滚"""
    print("⚠️  Downgrade options:")
    print("  1. Rollback one step (-1)")
    print("  2. Rollback to specific revision")
    choice = input("Choose (1/2): ").strip()
    
    if choice == "1":
        run_alembic_command(["downgrade", "-1"])
    elif choice == "2":
        revision = input("Target revision (e.g., base or revision ID): ").strip()
        run_alembic_command(["downgrade", revision])


async def reset_database():
    """重置数据库"""
    confirm = input("⚠️  This will DELETE ALL DATA. Type 'RESET' to confirm: ")
    if confirm != "RESET":
        print("Cancelled.")
        return
    
    from src.models.database import DatabaseManager
    db = DatabaseManager(DATABASE_URL)
    await db.drop_tables()
    print("All tables dropped!")
    
    # 重新建表
    run_migration()
    
    # 重新导入数据
    await init_database()
    
    await db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    commands = {
        "init": lambda: asyncio.run(init_database()),
        "migrate": run_migration,
        "revision": create_revision,
        "downgrade": run_downgrade,
        "history": show_history,
        "status": show_status,
        "reset": lambda: asyncio.run(reset_database()),
        "seed": lambda: asyncio.run(seed_sample_data(DatabaseManager(DATABASE_URL))),
        "backup": backup_database,
    }
    
    handler = commands.get(command)
    if handler:
        handler()
    else:
        print(f"❌ Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
