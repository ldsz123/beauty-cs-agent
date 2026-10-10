'use strict';

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
