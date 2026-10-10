"""
导入爬取数据到知识库
支持：内置模式（JSON文件）/ PostgreSQL 模式
"""
import asyncio
import json
import sys
import os
import glob
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from loguru import logger

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://cs_user:cs_pass_2024@localhost:5432/cs_agent"
)


def load_crawled_data() -> list[dict]:
    """加载爬取的数据（合并所有来源，去重）"""
    all_entries = []
    seen_titles = set()
    
    # 加载爬取数据（京东帮助中心）
    crawled_files = sorted(glob.glob("data/crawled/jd_crawled_*.json"))
    if crawled_files:
        latest = crawled_files[-1]  # 只用最新的
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)
        for entry in data:
            key = entry["title"][:50]
            if key not in seen_titles:
                seen_titles.add(key)
                all_entries.append(entry)
        logger.info(f"Loaded {len(data)} crawled entries from {latest}")
    
    # 加载精选补充数据
    supplement_files = sorted(glob.glob("data/crawled/crawled_kb_*.json"))
    if supplement_files:
        latest = supplement_files[-1]
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)
        added = 0
        for entry in data:
            key = entry.get("title", entry.get("question", ""))[:50]
            if key not in seen_titles:
                seen_titles.add(key)
                # 统一格式
                all_entries.append({
                    "category": entry.get("category", "常见问题"),
                    "title": entry.get("title", entry.get("question", ""))[:100],
                    "content": entry.get("answer", entry.get("content", "")),
                    "tags": entry.get("tags", []),
                    "source_url": entry.get("source_url", ""),
                    "crawled_at": entry.get("crawled_at", ""),
                })
                added += 1
        logger.info(f"Loaded {added} curated entries from {latest}")
    
    return all_entries


def clean_content(content: str) -> str:
    """清洗正文：去除日期行、多余空行"""
    import re
    lines = []
    for line in content.split("\n"):
        line = line.strip()
        # 跳过纯日期行
        if re.match(r'^\d{4}-\d{2}-\d{2}$', line):
            continue
        # 跳过太短的噪音行
        if len(line) < 2:
            continue
        lines.append(line)
    return "\n".join(lines)


async def import_to_postgres(entries: list[dict]):
    """导入 PostgreSQL"""
    from src.models.database import DatabaseManager, KnowledgeEntry
    from sqlalchemy import select, func
    
    db = DatabaseManager(DATABASE_URL)
    await db.create_tables()
    
    async with db.async_session_factory() as session:
        # 检查现有条数
        result = await session.execute(select(func.count(KnowledgeEntry.id)))
        existing_count = result.scalar()
        
        # 检查已存在的标题（避免重复导入）
        existing_result = await session.execute(select(KnowledgeEntry.title))
        existing_titles = {t for (t,) in existing_result.all()}
        
        added = 0
        for entry in entries:
            title = entry["title"][:100]
            if title in existing_titles:
                continue
            
            content = clean_content(entry.get("content", ""))
            if len(content) < 20:
                continue
            
            kb_entry = KnowledgeEntry(
                category=entry.get("category", "常见问题"),
                title=title,
                content=content,
                tags=entry.get("tags", []),
                priority=0,
            )
            session.add(kb_entry)
            added += 1
        
        await session.commit()
        
        result = await session.execute(select(func.count(KnowledgeEntry.id)))
        total = result.scalar()
        
        logger.info(f"Imported {added} new entries (existing: {existing_count}, total now: {total})")
    
    await db.close()
    return added


def import_to_builtin(entries: list[dict]):
    """导出为内置知识库 JSON（内存模式使用）"""
    output = []
    for entry in entries:
        content = clean_content(entry.get("content", ""))
        if len(content) < 20:
            continue
        output.append({
            "category": entry.get("category", "常见问题"),
            "content": content,
            "tags": entry.get("tags", []),
        })
    
    filepath = "data/knowledge_base/imported_kb.json"
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Exported {len(output)} entries to {filepath}")
    return len(output)


async def main():
    entries = load_crawled_data()
    logger.info(f"Total entries to import: {len(entries)}")
    
    if not entries:
        logger.error("No data to import! Run crawl_knowledge.py first.")
        return
    
    mode = os.environ.get("KB_MODE", "builtin")
    
    if mode in ("postgres", "redis"):
        added = await import_to_postgres(entries)
        print(f"\n✅ PostgreSQL import complete: {added} new entries")
    else:
        count = import_to_builtin(entries)
        print(f"\n✅ Built-in KB export complete: {count} entries")
        print(f"   File: data/knowledge_base/imported_kb.json")


if __name__ == "__main__":
    asyncio.run(main())
