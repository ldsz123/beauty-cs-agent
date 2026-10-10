"""
初始化知识库脚本
将知识库数据导入向量数据库
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def init_knowledge_base():
    """初始化知识库"""
    kb_data = [
        {
            "category": "退货政策",
            "content": "商品自签收之日起7天内可无理由退货，需保持商品完好、包装齐全。定制商品、生鲜食品、贴身衣物不支持无理由退货。",
            "tags": ["退货", "退款", "7天无理由", "退换货"]
        },
        {
            "category": "物流说明",
            "content": "订单确认后48小时内发货，一般3-5天送达。偏远地区可能延长至7天。如遇物流异常请联系客服。支持顺丰、京东、中通等多家快递。",
            "tags": ["物流", "快递", "发货", "配送", "运输"]
        },
        {
            "category": "支付方式",
            "content": "支持支付宝、微信支付、银行卡支付、花呗分期。如支付失败请检查网络或更换支付方式重试。支持合并支付和优惠券叠加。",
            "tags": ["支付", "付款", "支付宝", "微信", "分期"]
        },
        {
            "category": "售后服务",
            "content": "商品质量问题15天内可退换货，1年内保修。请保留好商品和包装以便处理售后。售后热线：400-xxx-xxxx。",
            "tags": ["售后", "保修", "质量问题", "换货", "维修"]
        },
        {
            "category": "优惠活动",
            "content": "新用户首单立减10元。满199减30，满299减50。会员享额外95折优惠。优惠券可在结算时使用。",
            "tags": ["优惠", "活动", "满减", "折扣", "优惠券", "红包"]
        },
        {
            "category": "订单修改",
            "content": "订单发货前可修改收货地址/手机号，发货后无法修改。请在下单后30分钟内完成修改。已发货订单如需修改请联系客服。",
            "tags": ["修改", "地址", "订单修改", "收货信息"]
        },
        {
            "category": "发票说明",
            "content": "支持开具电子发票和增值税专用发票。电子发票在订单完成后24小时内发送至您的邮箱。专用发票需提供完整的开票信息。",
            "tags": ["发票", "开票", "电子发票", "增值税"]
        },
        {
            "category": "账户安全",
            "content": "请妥善保管账户密码，不要与他人共享账户。支持手机验证码、密码、第三方登录等多种登录方式。如忘记密码可通过手机号找回。",
            "tags": ["账户", "登录", "密码", "安全", "绑定"]
        },
        {
            "category": "商品保障",
            "content": "所有商品均为正品保证，假一赔十。支持官方验货。商品图片可能与实物存在轻微色差，请以实物为准。",
            "tags": ["正品", "保障", "假货", "验货"]
        },
        {
            "category": "会员权益",
            "content": "注册即成为普通会员，累计消费满1000元升级为银卡会员，满5000元升级为金卡会员。不同等级享受不同折扣和专属服务。",
            "tags": ["会员", "等级", "权益", "积分", "VIP"]
        },
    ]
    
    # 保存为 JSON
    output_path = "data/knowledge_base/faq.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)
    
    print(f"Knowledge base initialized: {len(kb_data)} entries saved to {output_path}")
    
    # TODO: 导入向量数据库
    print("NOTE: Vector DB import will be implemented when Milvus is configured")


if __name__ == "__main__":
    init_knowledge_base()
