#!/usr/bin/env bash
# 鲲鹏运维平台 - Linux 裸机安装脚本 (systemd)
# 前置: 已安装 Python 3.11+ / PostgreSQL / Redis / Nginx
# 用法: sudo bash install.sh
set -euo pipefail

APP_NAME=kunpeng
INSTALL_DIR=/opt/$APP_NAME
VENV=$INSTALL_DIR/venv
SRC_DIR="$(cd "$(dirname "$0")/../.." && pwd)/backend"

echo "==> 安装目录: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
[ -d "$VENV" ] || python3 -m venv "$VENV"

echo "==> 安装 Python 依赖"
"$VENV/bin/pip" install -r "$SRC_DIR/requirements.txt"

echo "==> 写入环境配置"
if [ ! -f "$INSTALL_DIR/.env" ]; then
cat > "$INSTALL_DIR/.env" <<EOF
DATABASE_URL=postgresql+asyncpg://kunpeng:kunpeng@127.0.0.1:5432/kunpeng
REDIS_URL=redis://127.0.0.1:6379/0
SECRET_KEY=$(openssl rand -hex 32)
DATA_DIR=$INSTALL_DIR/data
EOF
fi

echo "==> 创建 systemd 服务"
cat > /etc/systemd/system/${APP_NAME}-api.service <<EOF
[Unit]
Description=KunpengRobot API
After=network.target postgresql.service redis.service

[Service]
WorkingDirectory=$SRC_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/${APP_NAME}-worker.service <<EOF
[Unit]
Description=KunpengRobot Analysis Worker
After=network.target ${APP_NAME}-api.service

[Service]
WorkingDirectory=$SRC_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV/bin/python -m app.worker
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ${APP_NAME}-api ${APP_NAME}-worker

echo "==> 完成"
echo "    API:    http://127.0.0.1:8000  (Nginx 反代配置见 deploy/nginx/nginx.conf)"
echo "    日志:   journalctl -u ${APP_NAME}-api -u ${APP_NAME}-worker -f"
