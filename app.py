# 飞书 x Muse 中转服务（FastAPI 模板）
# 所有密钥从环境变量读取，不要写死在代码里
import os
import json
import time
from collections import deque

import requests
from fastapi import FastAPI, Request

app = FastAPI()

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
# 你的 Muse 接口（按你实际用的填）
MUSE_API_URL = os.environ.get("MUSE_API_URL", "")
MUSE_API_KEY = os.environ.get("MUSE_API_KEY", "")

# 飞书会重试推送事件，用 message_id 去重（保留最近 1000 条）
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
    # TODO: 换成你真实的 Muse 调用，这里只是占位
    r = requests.post(
        MUSE_API_URL,
        headers={"Authorization": f"Bearer {MUSE_API_KEY}"},
        json={"message": user_text},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("reply", str(data))


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


@app.post("/webhook")
async def webhook(req: Request):
    body = await req.json()

    # 1. 飞书首次配置事件订阅时的 URL 校验
    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    # 2. 消息事件
    header = body.get("header", {})
    if header.get("event_type") == "im.message.receive_v1":
        event = body.get("event", {})
        msg = event.get("message", {})
        message_id = msg.get("message_id", "")

        # 去重：飞书可能重复推送同一条消息
        if not message_id or message_id in _seen_messages:
            return {"ok": True}
        _seen_messages.append(message_id)

        # 只处理文本消息
        if msg.get("message_type") != "text":
            return {"ok": True}

        content = json.loads(msg.get("content", "{}"))
        user_text = content.get("text", "")

        # 群聊 @ 机器人时，去掉 @ 标记再发给 Muse
        for mention in msg.get("mentions") or []:
            key = mention.get("key", "")
            if key:
                user_text = user_text.replace(key, "")
        user_text = user_text.strip()
        if not user_text:
            return {"ok": True}

        try:
            answer = ask_muse(user_text)
        except Exception as e:  # 别让异常吞掉飞书的回调
            answer = f"调用 Muse 出错了：{e}"

        try:
            reply_feishu(message_id, answer)
        except Exception as e:
            # 回复失败就记下来，别让飞书重试导致重复调用 Muse
            print(f"[feishu] reply failed: {e}")

    return {"ok": True}
