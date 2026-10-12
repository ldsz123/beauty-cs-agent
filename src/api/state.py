"""
共享应用状态
避免路由模块与 main 之间的循环导入
"""


class _AppState:
    """应用级状态持有者"""
    agent = None
    db_manager = None
    redis_cache = None


state = _AppState()
