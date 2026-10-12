#!/usr/bin/env bash
# 飞书 x Muse 机器人 - 国内服务器一键部署脚本
# 系统要求: Ubuntu/Debian + sudo 权限 + 公网 IP
# 用法:
#   curl -fsSLO https://raw.githubusercontent.com/liuw8233-cell/feishu-muse-bot/main/deploy.sh
#   bash deploy.sh
set -euo pipefail

APP_DIR="/opt/feishu-muse-bot"
REPO="https://github.com/liuw8233-cell/feishu-muse-bot.git"
SERVICE="feishu-muse-bot"

echo "== 1/5 检查基础环境 =="
if ! command -v python3 >/dev/null 2>&1; then
  echo "安装 python3..."
  sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-venv git curl
elif ! python3 -m venv --help >/dev/null 2>&1; then
  sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv
fi
command -v git >/dev/null 2>&1 || sudo apt-get install -y -qq git
command -v curl >/dev/null 2>&1 || sudo apt-get install -y -qq curl

echo "== 2/5 拉取代码 =="
# GitHub 直连不稳定时自动走加速镜像
git config --global http.lowSpeedLimit 1000 2>/dev/null || true
git config --global http.lowSpeedTime 60 2>/dev/null || true
try_clone() {
  rm -rf "$APP_DIR"
  sudo mkdir -p "$APP_DIR"
  sudo chown "$(id -un)":"$(id -gn)" "$APP_DIR"
  git clone --depth 1 "$1" "$APP_DIR"
}
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only || try_clone "$REPO"
else
  if ! try_clone "$REPO"; then
    echo "直连 GitHub 失败，尝试加速镜像..."
    try_clone "https://gh-proxy.com/https://github.com/liuw8233-cell/feishu-muse-bot.git" || \
    try_clone "https://mirror.ghproxy.com/https://github.com/liuw8233-cell/feishu-muse-bot.git" || \
    { echo "❌ 代码拉取失败，请检查服务器网络后重试"; exit 1; }
  fi
fi

echo "== 3/5 安装依赖（清华 pip 源）=="
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r "$APP_DIR/requirements.txt"

echo "== 4/5 配置环境变量 =="
ENV_FILE="$APP_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "首次部署，请输入飞书应用信息："
  read -rp "FEISHU_APP_ID: " APP_ID
  read -rsp "FEISHU_APP_SECRET: " APP_SECRET; echo
  printf 'FEISHU_APP_ID=%s\nFEISHU_APP_SECRET=%s\nMUSE_API_URL=\nMUSE_API_KEY=\nMUSE_MODEL=deepseek-chat\n' "$APP_ID" "$APP_SECRET" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "已写入 $ENV_FILE（Muse 接口地址以后再补）"
else
  echo "$ENV_FILE 已存在，跳过（如需修改请手动编辑后重启服务）"
fi

echo "== 5/5 注册 systemd 服务（开机自启） =="
sudo tee /etc/systemd/system/$SERVICE.service >/dev/null <<EOF
[Unit]
Description=Feishu x Muse bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(id -un)
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable -q "$SERVICE"
sudo systemctl restart "$SERVICE"
sleep 2
if sudo systemctl is-active -q "$SERVICE"; then
  echo "✅ 服务运行中"
else
  echo "❌ 服务启动失败，查看日志："
  sudo journalctl -u "$SERVICE" -n 20 --no-pager
  exit 1
fi

echo
echo "本地自检（应返回 challenge）："
curl -s -X POST http://127.0.0.1:8000/webhook \
  -H 'Content-Type: application/json' \
  -d '{"type":"url_verification","challenge":"hello"}'; echo
echo
echo "下一步："
echo "  1. 把域名解析到这台服务器，用反向代理指向 127.0.0.1:8000 并配好 HTTPS"
echo "    （宝塔面板建站 + 反向代理 + 一键 SSL 最省事）"
echo "  2. 去飞书开放平台 → 事件订阅 → 请求地址填 https://你的域名/webhook"
echo "  3. 添加事件 im.message.receive_v1，保存，发布版本，加群测试"
echo
echo "常用命令："
echo "  查看日志: sudo journalctl -u $SERVICE -f"
echo "  重启服务: sudo systemctl restart $SERVICE"
