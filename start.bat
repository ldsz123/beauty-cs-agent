@echo off
chcp 65001 >nul 2>&1
title 美妆电商智能客服 - 一键启动

echo ========================================
echo   美妆电商智能客服Agent - 一键启动
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 检查依赖
echo [1/4] 检查依赖...
python -c "import fastapi, uvicorn, loguru, pydantic, openai" >nul 2>&1
if errorlevel 1 (
    echo [提示] 安装依赖中...
    pip install -r requirements.txt -q
)

REM 初始化知识库（如果不存在）
echo [2/4] 初始化知识库...
if not exist "data\knowledge_base\skin_types.json" (
    python scripts/init_beauty_kb.py
)

REM 启动 PostgreSQL（Docker）
echo [3/4] 启动 PostgreSQL + Redis...
docker-compose up -d postgres redis >nul 2>&1
if errorlevel 1 (
    echo [提示] Docker 未运行，跳过数据库启动（使用内存模式）
    set SESSION_MODE=memory
    set KB_MODE=builtin
) else (
    REM 等待数据库就绪
    echo       等待 PostgreSQL 就绪...
    timeout /t 5 /nobreak >nul
    set SESSION_MODE=postgres
    set KB_MODE=postgres
)

REM 启动 API 服务
echo [4/4] 启动 API 服务...
echo.
echo ========================================
echo   服务已启动！
echo.
echo   聊天界面:   http://localhost:8000
echo   运营看板:   http://localhost:8000/dashboard
echo   API 文档:   http://localhost:8000/docs
echo   健康检查:   http://localhost:8000/api/health
echo   Metrics:    http://localhost:8000/metrics
echo.
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

set SESSION_MODE=postgres
set KB_MODE=postgres
python -m src.main

pause
