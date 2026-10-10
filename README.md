# 电商智能客服Agent

基于三级处理流水线的电商智能客服系统，支持 PostgreSQL + Redis 持久化 + Alembic 数据迁移。

## 架构

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  情感识别层  │ → │  语义分类层  │ → │  实体提取层  │
└─────────────┘   └─────────────┘   └─────────────┘
       │                 │                 │
       ▼                 ▼                 ▼
┌─────────────────────────────────────────────────┐
│           三级处理流水线（深度理解引擎）           │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│          响应生成 & 业务执行层                    │
└─────────────────────────────────────────────────┘

数据持久化层：
┌──────────┐  ┌──────────┐  ┌──────────┐
│ PostgreSQL│  │  Redis   │  │  Alembic │
│ (主存储)  │  │  (缓存)  │  │  (迁移)  │
└──────────┘  └──────────┘  └──────────┘
```

## 存储模式

| 模式 | 会话存储 | 知识库 | 适用场景 |
|------|---------|--------|---------|
| `memory` (默认) | 内存 | 内置数据 | 开发测试 |
| `postgres` | PostgreSQL | PostgreSQL | 单实例生产 |
| `redis` | PostgreSQL + Redis | PostgreSQL + Redis | 高性能生产 |

## 安全特性

- **API Key 认证**：所有 `/api/*` 端点需要 `X-API-Key` 请求头（可通过 `API_KEYS` 环境变量配置）
- **Rate Limiting**：基于 Redis 的滑动窗口限流（IP 60次/分钟，Session 20次/分钟）
- **输入验证**：消息长度限制、Prompt Injection 检测、控制字符过滤
- **CORS 白名单**：通过 `ALLOWED_ORIGINS` 环境变量配置允许的源
- **Redis 认证**：支持 Redis 密码认证

## 可观测性

- **结构化日志**：JSON 格式输出，包含 request_id、session_id 等上下文信息
- **Prometheus Metrics**：`/metrics` 端点暴露 HTTP/LLM/流水线指标
- **健康检查**：`/api/health`（Liveness）+ `/api/health/ready`（Readiness）
- **优雅关闭**：关闭时等待进行中请求完成，正确释放连接池

## 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY、DB_PASSWORD、REDIS_PASSWORD、API_KEYS

# 2. 一键启动（含 PostgreSQL + Redis + API）
docker-compose up -d

# 3. 初始化数据库（建表 + 导入数据）
docker-compose exec api python scripts/manage_db.py init
```

### 方式二：本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 PostgreSQL 和 Redis
docker-compose up -d postgres redis

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY

# 4. 初始化数据库
python scripts/manage_db.py init

# 5. 启动服务
python -m src.main

# 6. 打开聊天界面
# 浏览器访问 http://localhost:8000
```

## Web 聊天界面

启动服务后浏览器访问 `http://localhost:8000` 即可使用聊天界面：

- **情感可视化**：每条机器人回复下方显示识别到的情绪标签（😡 愤怒 / 😰 焦虑 / 😊 满意等）
- **意图标签**：显示识别到的用户意图（订单查询 / 物流查询 / 退货退款等）
- **响应耗时**：显示每次处理耗时（毫秒）
- **快捷提问**：欢迎卡片提供常见问题一键提问
- **转人工提示**：检测到强烈负面情绪时自动显示转人工横幅
- **新会话**：右上角按钮一键重置会话（清空历史 + 服务端会话重置）

界面文件位于 `static/` 目录（纯 HTML/CSS/JS，无需构建）：

```
static/
├── index.html   # 页面结构
├── style.css    # 样式
└── app.js       # 交互逻辑
```

## 数据库管理

### 数据库迁移（Alembic）

```bash
# 查看当前状态
python scripts/manage_db.py status

# 执行所有待执行的迁移
python scripts/manage_db.py migrate

# 创建新迁移（修改模型后自动生成）
python scripts/manage_db.py revision
# 输入迁移描述: "add_product_table"

# 回滚最后一次迁移
python scripts/manage_db.py downgrade

# 查看迁移历史
python scripts/manage_db.py history
```

### 数据库表结构

| 表名 | 说明 | 关键字段 |
|------|------|---------|
| `sessions` | 会话记录 | id, user_id, status, emotion_history |
| `conversations` | 对话消息 | session_id, role, content, intent, entities |
| `knowledge_base` | 知识库 | category, content, tags, embedding |
| `users` | 用户缓存 | id, phone, level, satisfaction_score |
| `escalations` | 转人工记录 | session_id, reason, resolved |
| `operation_logs` | 操作日志 | action, target, result |

### 数据备份

```bash
# 备份数据库
python scripts/manage_db.py backup
# 备份文件保存在 backups/ 目录
```

### 数据库连接配置

```bash
# 环境变量
DATABASE_URL=postgresql+asyncpg://cs_user:your_password@localhost:5432/cs_agent
REDIS_URL=redis://:your_password@localhost:6379
```

## API 接口

### 对话

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"message": "我的订单什么时候发货？", "session_id": "test-001"}'
```

### 带图片对话

```bash
curl -X POST http://localhost:8000/api/chat/with-image \
  -H "X-API-Key: your-api-key" \
  -F "message=这个商品有问题" \
  -F "session_id=test-001" \
  -F "image=@/path/to/image.png"
```

### 健康检查

```bash
# Liveness 探针
curl http://localhost:8000/api/health

# Readiness 探针
curl http://localhost:8000/api/health/ready
```

返回：
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "llm_available": true,
  "storage_mode": "redis",
  "db_connected": true,
  "redis_connected": true
}
```

### Prometheus Metrics

```bash
curl http://localhost:8000/metrics
```

## 测试

```bash
# 运行所有测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=src --cov-report=term-missing

# 运行特定测试文件
pytest tests/test_agent_engine.py -v
```

## 项目结构

```
├── src/
│   ├── main.py              # FastAPI 入口
│   ├── agent_engine.py      # 核心 Agent 引擎
│   ├── layers/              # 三级处理流水线
│   │   ├── emotion_layer.py     # 情感识别层
│   │   ├── semantic_layer.py    # 语义分类层
│   │   └── entity_layer.py      # 实体提取层
│   ├── modules/             # 功能模块
│   │   ├── vision_module.py     # 图理解模块
│   │   ├── session_manager.py   # 会话管理（3种模式）
│   │   └── knowledge_base.py    # 知识库（3种模式）
│   ├── models/              # 数据模型
│   │   ├── llm_client.py        # LLM 客户端
│   │   ├── database.py          # SQLAlchemy 模型
│   │   └── redis_client.py      # Redis 缓存
│   ├── services/            # 业务服务
│   │   └── action_executor.py   # 业务执行器
│   ├── middleware/          # 中间件
│   │   ├── auth.py              # API Key 认证
│   │   ├── rate_limit.py        # 限流器
│   │   ├── metrics.py           # Prometheus 指标
│   │   └── error_handler.py     # 异常处理器
│   ├── utils/               # 工具类
│   │   ├── sanitizer.py         # 输入清洗
│   │   ├── metrics.py           # 指标定义
│   │   └── logging_config.py    # 日志配置
│   └── exceptions.py        # 自定义异常
├── alembic/                 # 数据库迁移
│   ├── env.py               # 迁移环境配置
│   ├── script.py.mako       # 迁移脚本模板
│   └── versions/            # 迁移脚本
│       └── 20260928_000001_initial_schema.py
├── config/                  # 配置文件
├── scripts/
│   ├── manage_db.py         # 数据库管理（迁移+备份+初始化）
│   ├── init_kb.py           # 知识库导入
│   └── pg_init.sql          # PostgreSQL 初始化 SQL
├── backups/                 # 数据库备份目录
├── data/                    # 数据文件
│   └── knowledge_base/      # 知识库导入数据
├── static/                  # Web 聊天界面（纯静态，无需构建）
│   ├── index.html           # 页面结构
│   ├── style.css            # 样式
│   └── app.js               # 交互逻辑
├── tests/                   # 测试
│   ├── conftest.py          # pytest fixtures
│   ├── mocks/               # Mock 对象
│   │   └── llm_mock.py          # Mock LLM 客户端
│   ├── test_agent_engine.py # Agent 引擎测试
│   ├── test_session_manager.py # 会话管理测试
│   ├── test_knowledge_base.py  # 知识库测试
│   ├── test_action_executor.py # 业务执行器测试
│   ├── test_llm_client.py      # LLM 客户端测试
│   ├── test_api.py             # API 集成测试
│   ├── test_sanitizer.py       # 输入清洗测试
│   └── test_layers.py          # 三级流水线测试
├── .github/workflows/       # CI/CD
│   └── ci.yml                  # GitHub Actions 工作流
├── requirements.txt
├── pytest.ini               # pytest 配置
├── alembic.ini              # Alembic 配置
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## License

MIT
