"""
Agent 端到端测试
通过 API 测试三级流水线完整流程
"""
import httpx
import json
import asyncio

BASE_URL = "http://localhost:8000"

# 测试用例：(名称, 消息, 期望意图, 期望情感[可为None], 期望实体字段[可为None])
TEST_CASES = [
    # ===== 知识库检索类 =====
    ("发货时效咨询", "我的订单什么时候发货？", "order_status", None, None),
    ("退货流程咨询", "怎么退货退款？", "return_refund", None, None),
    ("运费咨询", "运费怎么算？满多少包邮？", "shipping_inquiry", None, None),
    ("发票咨询", "发票怎么开？可以开增值税发票吗？", "general_chat", None, None),
    ("账户问题", "忘记密码了怎么办？", "account_issue", None, None),
    # ===== 情感识别类 =====
    ("愤怒用户", "你们这是什么垃圾商家！太差了！我要投诉！", "complaint", "angry", None),
    ("焦虑用户", "我的快递怎么还没到啊？急死了，担心丢件", "shipping_inquiry", "anxious", None),
    ("满意用户", "商品质量不错，很满意，好评！", "general_chat", "satisfied", None),
    # ===== 实体提取类 =====
    ("订单号+查询", "帮我查一下订单TB20240101123456的状态", "order_status", None, "order_id"),
    ("手机号提供", "我的手机号是13812345678，帮我查下物流", "shipping_inquiry", None, "phone"),
    # ===== 转人工类 =====
    ("要求人工", "我要找人工客服", "escalate", None, None),
    # ===== 闲聊 =====
    ("打招呼", "你好呀", "general_chat", "neutral", None),
]


async def run_test(client: httpx.AsyncClient, name: str, message: str,
                   expect_intent: str, expect_emotion: str, expect_entity: str,
                   session_id: str) -> dict:
    """运行单个测试"""
    try:
        resp = await client.post(f"{BASE_URL}/api/chat", json={
            "message": message,
            "session_id": session_id,
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"name": name, "pass": False, "error": str(e)}
    
    checks = []
    
    # 意图检查
    intent = data["intent"]
    intent_ok = intent == expect_intent
    checks.append(("intent", intent_ok, f"{intent} (期望 {expect_intent})"))
    
    # 情感检查
    emotion = data["emotion"]["type"]
    if expect_emotion:
        emotion_ok = emotion == expect_emotion
        checks.append(("emotion", emotion_ok, f"{emotion} (期望 {expect_emotion})"))
    else:
        checks.append(("emotion", True, f"{emotion}"))
    
    # 实体检查
    if expect_entity:
        entity_val = data["entities"].get(expect_entity)
        entity_ok = entity_val is not None
        checks.append(("entity", entity_ok, f"{expect_entity}={entity_val}"))
    
    # 回复非空
    reply_ok = len(data["reply"]) > 0
    checks.append(("reply", reply_ok, data["reply"][:60]))
    
    all_pass = all(c[1] for c in checks)
    
    return {
        "name": name,
        "pass": all_pass,
        "checks": checks,
        "need_human": data["need_human"],
        "time_ms": data["processing_time_ms"],
        "kb_used": len(data.get("actions", [])) > 0,
    }


async def main():
    results = []
    async with httpx.AsyncClient() as client:
        # 健康检查
        resp = await client.get(f"{BASE_URL}/api/health", timeout=10)
        health = resp.json()
        print(f"服务状态: {health['status']} | 存储: {health['storage_mode']} | LLM: {health['llm_available']}")
        print("=" * 80)
        
        for i, (name, message, intent, emotion, entity) in enumerate(TEST_CASES):
            result = await run_test(client, name, message, intent, emotion, entity,
                                    session_id=f"test-{i}")
            results.append(result)
            
            status = "✅ PASS" if result["pass"] else "❌ FAIL"
            print(f"{status} [{name}] 消息: {message}")
            if result.get("error"):
                print(f"      错误: {result['error']}")
            for check_name, ok, detail in result.get("checks", []):
                mark = "✓" if ok else "✗"
                print(f"      {mark} {check_name}: {detail}")
            print(f"      耗时: {result.get('time_ms', '?')}ms | 转人工: {result.get('need_human')}")
            print("-" * 80)
        
        # 汇总
        passed = sum(1 for r in results if r["pass"])
        total = len(results)
        print(f"\n测试结果: {passed}/{total} 通过 ({passed/total*100:.0f}%)")
        
        # 失败项
        failures = [r for r in results if not r["pass"]]
        if failures:
            print(f"\n失败用例: {[f['name'] for f in failures]}")


if __name__ == "__main__":
    asyncio.run(main())
