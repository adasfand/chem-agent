#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "已创建 .env；请填写 DeepSeek 密钥或密钥文件路径。"
fi
if command -v conda >/dev/null 2>&1; then
  exec conda run --no-capture-output -n chem-agent python app.py
else
  echo "请先配置 Conda 和 chem-agent 环境，再运行本脚本。"
  exit 1
fi
