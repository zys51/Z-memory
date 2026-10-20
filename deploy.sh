#!/usr/bin/env bash
# AML Memory Service 一键部署脚本（Ubuntu/Debian，以 root 运行）
# 用法：先把代码放到 ~/memcomp，然后：
#   cd ~/memcomp && DASHSCOPE_API_KEY=sk-你的key bash deploy.sh
# 可选再传 AML_API_KEY（评测 Key，可部署后再填 .env 并重启）：
#   AML_API_KEY=xxx DASHSCOPE_API_KEY=sk-xxx bash deploy.sh
set -euo pipefail

# 0) 前置检查：必须带嵌入 Key，否则后面会以占位符运行导致 401
if [ -z "${DASHSCOPE_API_KEY:-}" ]; then
  echo "错误：未提供 DASHSCOPE_API_KEY"
  echo "  请这样运行：DASHSCOPE_API_KEY=sk-你的key bash deploy.sh"
  exit 1
fi

echo "==> [1/6] 安装系统依赖"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl

echo "==> [2/6] 创建虚拟环境并安装依赖（清华镜像）"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

echo "==> [3/6] 配置 .env"
[ -f .env ] || cp .env.example .env
sed -i "s|^DASHSCOPE_API_KEY=.*|DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}|" .env
if [ -n "${AML_API_KEY:-}" ]; then
  sed -i "s|^AML_API_KEY=.*|AML_API_KEY=${AML_API_KEY}|" .env
fi
echo "    当前 .env（密钥已隐藏）："
sed -E 's/(=).*/\1****/' .env

echo "==> [4/6] 验证嵌入 Key 可用"
.venv/bin/python - <<'PY'
import asyncio
from app.embedder import Embedder
vecs = asyncio.run(Embedder().embed(["hello"], text_type="document"))
print("    Key OK, dim =", len(vecs[0]))
PY

echo "==> [5/6] 安装并启动 systemd 服务"
cat > /etc/systemd/system/memcomp.service <<EOF
[Unit]
Description=AML Memory Service
After=network.target

[Service]
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/python run.py
Restart=always
EnvironmentFile=$(pwd)/.env

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now memcomp

echo "==> [6/6] 健康检查"
sleep 2
if curl -fsS http://127.0.0.1:8080/health; then
  echo ""
  echo "部署成功！服务运行在 :8080"
else
  echo "健康检查失败，查看日志：journalctl -u memcomp -n 50"
  exit 1
fi
