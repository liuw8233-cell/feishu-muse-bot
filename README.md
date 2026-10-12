# 飞书 x Muse 最小接入方案

## 架构（长连接模式）
飞书（WebSocket 长连接推送事件） → 本服务 → 大模型 API（OpenAI 兼容） → 引用原消息回复

**长连接模式不需要公网域名、不需要 HTTPS、不需要反向代理/内网穿透**，
服务只要能出站访问公网就能跑。

## 飞书侧配置（两种部署方式通用）

1. 飞书开放平台 → 你的应用 →「事件订阅」→ 订阅方式选「**使用长连接接收事件**」
2. 权限管理确认三个权限：
   - `im:message.p2p_msg:readonly`（收私聊）
   - `im:message.group_at_msg:readonly`（群里被 @ 时收消息）
   - `im:message:send_as_bot`（以机器人身份发消息）
   - 可选加 `im:resource`（收图片/文件）
3. 确认已开启「机器人」应用能力
4. 「事件订阅」里添加事件 `im.message.receive_v1`（加密策略保持关闭）
5. **去「版本管理与发布」创建并发布新版本**（改了订阅方式/权限必须重新发布才生效）
6. 把机器人拉进群，@ 它说话即可

> ⚠️ 同一时间只能用一种订阅模式（长连接 或 回调），不要两个都开，否则会重复收消息。

## 自有服务器部署（推荐）

一键脚本（Ubuntu/Debian，国内 pip 源、systemd 开机自启都配好了）：
```bash
curl -fsSLO https://raw.githubusercontent.com/liuw8233-cell/feishu-muse-bot/main/deploy.sh
bash deploy.sh
```
脚本会提示你填写 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`，
以及大模型配置（`MUSE_API_URL` / `MUSE_API_KEY` / `MUSE_MODEL`，三选一）：
- DeepSeek：`https://api.deepseek.com` + `deepseek-chat`
- Kimi：`https://api.moonshot.cn` + `kimi-k2`
- 通义：`https://dashscope.aliyuncs.com/compatible-mode/v1` + `qwen-plus`

跑完即用，不需要域名和 HTTPS。

## 部署到 Sealos（备选）

长连接模式下 Sealos 不是必需的；如果想用，流程同上，
只是把代码换成容器方式跑（Dockerfile 已提供），环境变量照填即可。

## 手动部署
```bash
pip install -r requirements.txt
cp .env.example .env   # 填好你的密钥和大模型配置
uvicorn app:app --host 0.0.0.0 --port 8000
```

## 安全提醒
- App Secret 只放在环境变量 / 服务器的密钥管理里，不要写进代码、不要发到聊天记录
- 如果 Secret 已经发到过聊天，建议去飞书后台重置一次

## 待办
- 无，`ask_muse()` 已支持所有 OpenAI 兼容接口

## 更新记录
- 2026-10-12：**改走 WebSocket 长连接模式**（`lark-oapi`），不再需要公网域名/HTTPS/反向代理；飞书侧把事件订阅改为「使用长连接接收事件」并重新发布版本；`ask_muse()` 改为 OpenAI 兼容接口，支持 DeepSeek/Kimi/通义。
- 2026-10-12：修复回复逻辑——改用 `POST /im/v1/messages/:message_id/reply` 引用原消息回复；新增消息去重、@ 标记剥离、token 缓存。
