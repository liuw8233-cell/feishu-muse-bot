# 飞书 x Muse 最小接入方案

## 架构
飞书（收发消息） → 本服务 `/webhook` → Muse API → 回复写回飞书

## 部署到 Sealos（推荐，免费额度够跑）

1. 把本目录推到你的 GitHub 仓库（已含 Dockerfile）
2. 登录 Sealos Cloud → 桌面 → 打开「应用管理」（App Launchpad）→ 新建应用
3. 选择从源码仓库部署，填你的 GitHub 仓库地址
4. 表单里配置：
   - 容器暴露端口：`8000`，并开启外网访问
   - 环境变量：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`MUSE_API_URL`、`MUSE_API_KEY`
   - CPU/内存选最小档即可（如 0.5C / 512M）
5. 点部署，等状态变 Running，复制它给的公网地址
6. 回飞书开放平台 → 事件订阅 → 请求地址填 `https://你的sealos域名/webhook`，
   添加事件 `im.message.receive_v1` 后保存（URL 校验会自动通过）
7. 发布应用版本，加到群里 @ 它测试

注意：Sealos 按量计费，新用户一般有免费试用额度，跑这个小服务很省；
`MUSE_API_URL` 没准备好可以先留空占位，飞书校验能过，只是对话回复会报错，
等接口 ready 了在应用详情页更新环境变量后重部署即可。

## 本地/自有服务器部署
1. 飞书开放平台 → 自建应用 → 开通「机器人」能力
2. 「事件订阅」添加 `im.message.receive_v1`，请求地址填 `https://你的域名/webhook`
   - 首次保存时飞书会发 `url_verification`，本模板已处理
3. 部署本服务：
   ```bash
   pip install -r requirements.txt
   cp .env.example .env   # 填好你的密钥
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```
4. 把应用发布并加到群里，@ 它说话即可

## 安全提醒
- App Secret 只放在环境变量 / 服务器的密钥管理里，不要写进代码、不要发到聊天记录
- 如果 Secret 已经发到过聊天，建议去飞书后台重置一次

## 待办（按你的 Muse 接口改）
- `ask_muse()` 目前是占位实现，换成你真实的 Muse 调用即可

## 更新记录
- 2026-10-12：修复回复逻辑——改用 `POST /im/v1/messages/:message_id/reply` 引用原消息回复（之前版本用 `im/v1/messages` + `receive_id_type=open_message_id`，该参数值飞书不支持，测试时会报参数错误）；新增消息去重（飞书会重试推送）、@ 标记剥离、token 缓存。
