# 飞书 x Muse 中转服务（长连接模式）
#
# 飞书侧把事件订阅设为「使用长连接接收事件」后，服务主动连飞书收消息，
# 不需要公网域名、不需要 HTTPS、不需要反向代理/内网穿透。
# 所有密钥从环境变量读取，不要写死在代码里。
import os
import json
import time
import threading
from collections import deque

import requests
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from fastapi import FastAPI

app = FastAPI()

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
# OpenAI 兼容的大模型接口
MUSE_API_URL = os.environ.get("MUSE_API_URL", "").rstrip("/")
MUSE_API_KEY = os.environ.get("MUSE_API_KEY", "")
MUSE_MODEL = os.environ.get("MUSE_MODEL", "deepseek-chat")

# 飞书可能重复推送事件，用 message_id 去重（保留最近 1000 条）
_seen_messages = deque(maxlen=1000)

# tenant_access_token 有效期约 2 小时，简单缓存避免每次都换
_token_cache = {"token": "", "expire_at": 0}


def get_tenant_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expire_at"]:
        return _token_cache["token"]
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    _token_cache["token"] = data["tenant_access_token"]
    # 提前 5 分钟过期，留出余量
    _token_cache["expire_at"] = time.time() + data.get("expire", 7200) - 300
    return _token_cache["token"]


def ask_muse(user_text: str) -> str:
    """调用 OpenAI 兼容的大模型接口。
    DeepSeek: MUSE_API_URL=https://api.deepseek.com, MUSE_MODEL=deepseek-chat
    Kimi:     MUSE_API_URL=https://api.moonshot.cn, MUSE_MODEL=kimi-k2
    通义:     MUSE_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1, MUSE_MODEL=qwen-plus
    """
    r = requests.post(
        f"{MUSE_API_URL}/chat/completions",
        headers={"Authorization": f"Bearer {MUSE_API_KEY}"},
        json={
            "model": MUSE_MODEL,
            "messages": [{"role": "user", "content": user_text}],
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def reply_feishu(message_id: str, text: str) -> None:
    """引用原消息回复：POST /im/v1/messages/:message_id/reply"""
    token = get_tenant_token()
    r = requests.post(
        f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        timeout=10,
    )
    r.raise_for_status()


def process_message(message_id: str, message_type: str, content_json: str, mentions) -> None:
    """处理一条消息：去重 → 只收文本 → 去 @ 标记 → 问大模型 → 引用回复"""
    if not message_id or message_id in _seen_messages:
        return
    _seen_messages.append(message_id)

    if "text" not in str(message_type):
        return

    try:
        user_text = json.loads(content_json or "{}").get("text", "")
    except Exception:
        return

    # 群聊 @ 机器人时，去掉 @ 标记再发给大模型
    for m in mentions or []:
        key = m.get("key", "") if isinstance(m, dict) else getattr(m, "key", "")
        if key:
            user_text = user_text.replace(key, "")
    user_text = user_text.strip()
    if not user_text:
        return

    if not MUSE_API_URL or not MUSE_API_KEY:
        answer = "我还没接上大模型，配置好 API Key 后我就能聊天了"
    else:
        try:
            answer = ask_muse(user_text)
        except Exception as e:  # 别让异常影响长连接
            answer = f"调用大模型出错了：{e}"

    try:
        reply_feishu(message_id, answer)
    except Exception as e:
        print(f"[feishu] reply failed: {e}", flush=True)


def _on_message(data: P2ImMessageReceiveV1) -> None:
    """长连接收到 im.message.receive_v1 事件。丢到线程里处理，避免阻塞心跳。"""
    msg = data.event.message
    mentions = [{"key": getattr(m, "key", "")} for m in (msg.mentions or [])]
    threading.Thread(
        target=process_message,
        args=(msg.message_id, msg.message_type, msg.content, mentions),
        daemon=True,
    ).start()


def _run_ws() -> None:
    # verification_token / encrypt_key 传空 = 加密策略关闭，和飞书后台保持一致
    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message)
        .build()
    )
    cli = lark.ws.Client(
        FEISHU_APP_ID,
        FEISHU_APP_SECRET,
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
    )
    print("[feishu] 长连接启动，等待消息…", flush=True)
    cli.start()


@app.on_event("startup")
def _startup() -> None:
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        print("[feishu] 未配置 FEISHU_APP_ID/SECRET，长连接未启动", flush=True)
        return
    threading.Thread(target=_run_ws, daemon=True).start()


@app.get("/health")
def health():
    return {"ok": True, "mode": "long-connection"}
