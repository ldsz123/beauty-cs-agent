-- PostgreSQL 初始化脚本
-- Docker 首次启动时自动执行

-- 启用 pgvector 扩展（如果镜像自带则跳过）
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- 全文搜索支持

-- 设置时区
SET timezone = 'Asia/Shanghai';

-- 创建初始 schema（SQLAlchemy 会自动建表，这里只做补充）
-- 如需手动建表，取消下面的注释：

-- CREATE TABLE IF NOT EXISTS sessions (
--     id VARCHAR(64) PRIMARY KEY,
--     user_id VARCHAR(64),
--     status VARCHAR(20) DEFAULT 'active',
--     created_at TIMESTAMP DEFAULT NOW(),
--     updated_at TIMESTAMP DEFAULT NOW(),
--     ended_at TIMESTAMP,
--     emotion_history JSONB DEFAULT '[]',
--     context JSONB DEFAULT '{}',
--     unresolved_count INTEGER DEFAULT 0,
--     metadata JSONB DEFAULT '{}'
-- );

-- 创建索引（SQLAlchemy 会自动创建，这里做备份）
-- CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
-- CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
-- CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at);
