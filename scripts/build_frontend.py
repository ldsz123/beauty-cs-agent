#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
前端构建脚本
分段生成 index.html / style.css / app.js，避免大文件写入时内容混乱
"""
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
STATIC.mkdir(exist_ok=True)

# ============================================================
# CSS — 设计令牌统一，类名统一
# ============================================================
CSS = """
:root {
  --bg: #f3f5fb;
  --card: #ffffff;
  --border: #e4e8f2;
  --text: #1f2430;
  --text2: #6b7280;
  --primary: #4f6ef7;
  --primary-dark: #3b56d9;
  --success: #10b981;
  --danger: #ef4444;
  --radius: 14px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; }
body {
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  display: flex;
  justify-content: center;
}

/* ===== 应用容器 ===== */
.app {
  width: min(880px, 100%);
  height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ===== 顶栏 ===== */
.topbar {
  background: var(--card);
  border-bottom: 1px solid var(--border);
  padding: 13px 20px;
  display: flex;
  align-items: center;
  gap: 13px;
  flex-shrink: 0;
}
.topbar-logo {
  width: 42px; height: 42px;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--primary), #8b5cf6);
  display: flex; align-items: center; justify-content: center;
  font-size: 21px;
  flex-shrink: 0;
}
.topbar-main { flex: 1; min-width: 0; }
.topbar-title { font-size: 16.5px; font-weight: 700; }
.topbar-sub {
  display: flex; align-items: center; gap: 12px;
  font-size: 12px; color: var(--text2); margin-top: 3px;
}
.status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--success);
  display: inline-block; margin-right: 5px;
}
.status-dot.bad { background: var(--danger); }
.btn-new {
  background: var(--primary); color: #fff;
  border: none; border-radius: 10px;
  padding: 9px 17px; font-size: 13.5px;
  cursor: pointer; transition: background .2s;
  flex-shrink: 0;
}
.btn-new:hover { background: var(--primary-dark); }

/* ===== 转人工横幅 ===== */
#humanBanner {
  display: none;
  background: #fff5f5;
  border-bottom: 1px solid #fecaca;
  color: #b91c1c;
  font-size: 13.5px;
  padding: 10px 20px;
  flex-shrink: 0;
}
#humanBanner.show { display: block; }

/* ===== 聊天区 ===== */
#chatBox {
  flex: 1;
  overflow-y: auto;
  padding: 22px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
#chatBox::-webkit-scrollbar { width: 6px; }
#chatBox::-webkit-scrollbar-thumb {
  background: #ccd3e8; border-radius: 3px;
}

.msg-row { display: flex; gap: 10px; max-width: 86%; }
.msg-row.user { align-self: flex-end; flex-direction: row-reverse; }

.avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 17px;
  flex-shrink: 0;
}
.avatar.bot { background: linear-gradient(135deg, var(--primary), #8b5cf6); color: #fff; }
.avatar.user { background: #e0e5f7; }

.msg-body { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.msg-row.user .msg-body { align-items: flex-end; }

.bubble {
  padding: 11px 15px;
  border-radius: var(--radius);
  font-size: 14.5px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble.bot {
  background: var(--card);
  border: 1px solid var(--border);
  border-top-left-radius: 5px;
}
.bubble.user {
  background: var(--primary);
  color: #fff;
  border-top-right-radius: 5px;
}

.meta-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag {
  font-size: 11.5px;
  padding: 2.5px 10px;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text2);
}
.tag.emotion-angry { background: #fef2f2; color: #dc2626; border-color: #fecaca; }
.tag.emotion-anxious { background: #fffbeb; color: #d97706; border-color: #fde68a; }
.tag.emotion-satisfied { background: #ecfdf5; color: #059669; border-color: #a7f3d0; }
.tag.emotion-grateful { background: #fdf4ff; color: #a21caf; border-color: #f5d0fe; }
.tag.emotion-urgent { background: #fff7ed; color: #ea580c; border-color: #fed7aa; }
.tag.intent { background: #eef2ff; color: #4f46e5; border-color: #e0e7ff; }
.tag.time { background: transparent; border-color: transparent; }

/* ===== 打字中 ===== */
.typing { display: inline-flex; gap: 4px; padding: 4px 2px; }
.typing span {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #b9c1d9;
  animation: typing-bounce 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: .15s; }
.typing span:nth-child(3) { animation-delay: .3s; }
@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-5px); }
}

/* ===== 欢迎卡片 ===== */
#welcome {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 26px 22px;
  text-align: center;
  align-self: center;
  max-width: 560px;
}
#welcome h2 { font-size: 17px; margin-bottom: 7px; }
#welcome p { font-size: 13.5px; color: var(--text2); margin-bottom: 16px; line-height: 1.6; }
.quick-asks {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  justify-content: center;
}
.quick-ask {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 8px 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all .2s;
}
.quick-ask:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: #eef2ff;
}

/* ===== 输入区 ===== */
.input-area {
  background: var(--card);
  border-top: 1px solid var(--border);
  padding: 13px 20px 9px;
  flex-shrink: 0;
}
.input-wrap {
  display: flex;
  align-items: flex-end;
  gap: 9px;
  background: var(--bg);
  border: 1.5px solid var(--border);
  border-radius: 12px;
  padding: 5px 5px 5px 15px;
  transition: border-color .2s;
}
.input-wrap:focus-within { border-color: var(--primary); }
#msgInput {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-family: inherit;
  font-size: 14.5px;
  line-height: 1.5;
  padding: 8px 0;
  resize: none;
  max-height: 110px;
}
#sendBtn {
  width: 42px; height: 38px;
  border: none;
  border-radius: 9px;
  background: var(--primary);
  color: #fff;
  font-size: 16px;
  cursor: pointer;
  transition: background .2s;
  flex-shrink: 0;
}
#sendBtn:hover { background: var(--primary-dark); }
#sendBtn:disabled { background: #c3cbe8; cursor: not-allowed; }
.input-hint {
  text-align: center;
  font-size: 11.5px;
  color: var(--text2);
  margin-top: 7px;
}

@media (max-width: 600px) {
  .msg-row { max-width: 95%; }
  .topbar, .input-area { padding-left: 13px; padding-right: 13px; }
  #chatBox { padding-left: 13px; padding-right: 13px; }
}
"""

# ============================================================
# HTML 结构 — 类名与 CSS 一致
# ============================================================
HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>电商智能客服 Agent</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="app">

  <div class="topbar">
    <div class="topbar-logo">🤖</div>
    <div class="topbar-main">
      <div class="topbar-title">电商智能客服 Agent</div>
      <div class="topbar-sub">
        <span><span class="status-dot" id="statusDot"></span><span id="statusText">连接中…</span></span>
        <span id="storageInfo"></span>
      </div>
    </div>
    <button class="btn-new" onclick="newSession()">＋ 新会话</button>
  </div>

  <div id="humanBanner">⚠️ 检测到您需要人工服务，正在为您转接人工客服，请稍候…</div>

  <div id="chatBox">
    <div id="welcome">
      <h2>👋 您好，我是电商智能客服</h2>
      <p>支持订单查询、物流跟踪、退换货、发票、账户等咨询，还能识别您的情绪哦</p>
      <div class="quick-asks">
        <span class="quick-ask" onclick="quickAsk(this)">我的订单什么时候发货？</span>
        <span class="quick-ask" onclick="quickAsk(this)">运费怎么算？满多少包邮？</span>
        <span class="quick-ask" onclick="quickAsk(this)">怎么退货退款？</span>
        <span class="quick-ask" onclick="quickAsk(this)">发票怎么开？</span>
        <span class="quick-ask" onclick="quickAsk(this)">忘记密码了怎么办？</span>
      </div>
    </div>
  </div>

  <div class="input-area">
    <div class="input-wrap">
      <textarea id="msgInput" rows="1" placeholder="请输入您的问题，回车发送…"
        onkeydown="onKeyDown(event)" oninput="autoGrow(this)"></textarea>
      <button id="sendBtn" onclick="sendMessage()">➤</button>
    </div>
    <div class="input-hint">Enter 发送 · Shift+Enter 换行</div>
  </div>

</div>
<script src="/static/app.js"></script>
</body>
</html>
"""

# ============================================================
# JS — 函数名统一：addMessage / showTyping / hideTyping / sendMessage / newSession / quickAsk
# ============================================================
JS = """'use strict';

// ===== 全局状态 =====
var sessionId = 'web-' + Date.now().toString(36);
var sending = false;

var EMOTION_TEXT = {
  angry: '😡 愤怒', anxious: '😰 焦虑', urgent: '⚡ 紧急',
  dissatisfied: '😕 不满', neutral: '😐 中性', satisfied: '😊 满意', grateful: '🙏 感激'
};
var INTENT_TEXT = {
  product_inquiry: '商品咨询', price_inquiry: '价格咨询', promotion_inquiry: '促销咨询',
  comparison: '商品对比', order_status: '订单查询', order_modify: '订单修改',
  payment_issue: '支付问题', shipping_inquiry: '物流查询', return_refund: '退货退款',
  exchange: '换货', complaint: '投诉', warranty: '保修售后', account_issue: '账户问题',
  tech_support: '技术支持', general_chat: '通用咨询', escalate: '转人工'
};

// ===== 元素引用 =====
var chatBox = document.getElementById('chatBox');
var msgInput = document.getElementById('msgInput');
var sendBtn = document.getElementById('sendBtn');
var statusDot = document.getElementById('statusDot');
var statusText = document.getElementById('statusText');
var storageInfo = document.getElementById('storageInfo');
var humanBanner = document.getElementById('humanBanner');

// ===== 健康检查 =====
async function checkHealth() {
  try {
    var resp = await fetch('/api/health');
    var data = await resp.json();
    if (data.status === 'healthy') {
      statusText.textContent = data.llm_available ? 'LLM 已接入' : '规则模式';
      storageInfo.textContent = '存储: ' + data.storage_mode;
    } else {
      statusText.textContent = '服务异常';
      statusDot.classList.add('bad');
    }
  } catch (e) {
    statusText.textContent = '无法连接服务';
    statusDot.classList.add('bad');
  }
}

// ===== 消息渲染 =====
function removeWelcome() {
  var w = document.getElementById('welcome');
  if (w) w.remove();
}

function addMessage(role, content, meta) {
  removeWelcome();

  var row = document.createElement('div');
  row.className = 'msg-row ' + (role === 'user' ? 'user' : 'bot');

  var avatar = document.createElement('div');
  avatar.className = 'avatar ' + (role === 'user' ? 'user' : 'bot');
  avatar.textContent = role === 'user' ? '🧑' : '🤖';

  var body = document.createElement('div');
  body.className = 'msg-body';

  var bubble = document.createElement('div');
  bubble.className = 'bubble ' + (role === 'user' ? 'user' : 'bot');
  bubble.textContent = content;
  body.appendChild(bubble);

  if (role === 'bot' && meta) {
    var tags = document.createElement('div');
    tags.className = 'meta-tags';

    if (meta.emotion && EMOTION_TEXT[meta.emotion]) {
      var t1 = document.createElement('span');
      t1.className = 'tag emotion-' + meta.emotion;
      t1.textContent = EMOTION_TEXT[meta.emotion];
      tags.appendChild(t1);
    }
    if (meta.intent && INTENT_TEXT[meta.intent]) {
      var t2 = document.createElement('span');
      t2.className = 'tag intent';
      t2.textContent = INTENT_TEXT[meta.intent];
      tags.appendChild(t2);
    }
    if (meta.time !== undefined) {
      var t3 = document.createElement('span');
      t3.className = 'tag time';
      t3.textContent = meta.time + 'ms';
      tags.appendChild(t3);
    }
    if (tags.children.length > 0) {
      body.appendChild(tags);
    }
  }

  row.appendChild(avatar);
  row.appendChild(body);
  chatBox.appendChild(row);
  chatBox.scrollTop = chatBox.scrollHeight;
}

// ===== 打字中 =====
function showTyping() {
  removeWelcome();
  var row = document.createElement('div');
  row.className = 'msg-row bot';
  row.id = 'typingRow';
  row.innerHTML =
    '<div class="avatar bot">🤖</div>' +
    '<div class="msg-body"><div class="bubble bot">' +
    '<span class="typing"><span></span><span></span><span></span></span>' +
    '</div></div>';
  chatBox.appendChild(row);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function hideTyping() {
  var t = document.getElementById('typingRow');
  if (t) t.remove();
}

// ===== 发送消息 =====
async function sendMessage() {
  var message = msgInput.value.trim();
  if (!message || sending) return;

  sending = true;
  sendBtn.disabled = true;
  msgInput.value = '';
  msgInput.style.height = 'auto';

  addMessage('user', message);
  showTyping();

  try {
    var resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message, session_id: sessionId })
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var data = await resp.json();

    hideTyping();
    addMessage('bot', data.reply, {
      emotion: data.emotion ? data.emotion.type : null,
      intent: data.intent,
      time: data.processing_time_ms
    });

    if (data.need_human) {
      humanBanner.classList.add('show');
      setTimeout(function () { humanBanner.classList.remove('show'); }, 8000);
    }
  } catch (e) {
    hideTyping();
    addMessage('bot', '抱歉，服务暂时不可用，请稍后重试。');
  } finally {
    sending = false;
    sendBtn.disabled = false;
    msgInput.focus();
  }
}

// ===== 交互事件 =====
function onKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function autoGrow(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 110) + 'px';
}

function quickAsk(el) {
  msgInput.value = el.textContent;
  sendMessage();
}

// ===== 新会话 =====
async function newSession() {
  try {
    await fetch('/api/session/' + sessionId, { method: 'DELETE' });
  } catch (e) {}
  sessionId = 'web-' + Date.now().toString(36);

  chatBox.innerHTML =
    '<div id="welcome">' +
    '<h2>👋 您好，我是电商智能客服</h2>' +
    '<p>支持订单查询、物流跟踪、退换货、发票、账户等咨询，还能识别您的情绪哦</p>' +
    '<div class="quick-asks">' +
    '<span class="quick-ask" onclick="quickAsk(this)">我的订单什么时候发货？</span>' +
    '<span class="quick-ask" onclick="quickAsk(this)">运费怎么算？满多少包邮？</span>' +
    '<span class="quick-ask" onclick="quickAsk(this)">怎么退货退款？</span>' +
    '<span class="quick-ask" onclick="quickAsk(this)">发票怎么开？</span>' +
    '<span class="quick-ask" onclick="quickAsk(this)">忘记密码了怎么办？</span>' +
    '</div></div>';
  msgInput.focus();
}

// ===== 初始化 =====
checkHealth();
msgInput.focus();
"""

# ============================================================
# 写入文件
# ============================================================
(STATIC / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")
(STATIC / "app.js").write_text(JS.strip() + "\n", encoding="utf-8")
(STATIC / "index.html").write_text(HTML, encoding="utf-8")

print(f"✅ 前端文件生成完成 → {STATIC}")
for f in ["style.css", "app.js", "index.html"]:
    p = STATIC / f
    print(f"   {f}: {p.stat().st_size} bytes")
