#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "已创建 .env；请填写 DeepSeek 密钥或密钥文件路径。"
fi
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python app.py
elif command -v uv >/dev/null 2>&1; then
  uv sync --locked --no-dev
  exec uv run --no-sync python app.py
else
  echo "请先安装 Python 3.11–3.13 和 uv，然后运行 uv sync --locked。"
  exit 1
fi
