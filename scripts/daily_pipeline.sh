#!/bin/bash
# Daily English — Hermes cron 入口脚本
# 由 Hermes cron 每日调用
# 
# 用法: 直接执行即可

set -eo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR=$(pwd)

# 加载环境变量
export $(grep -v '^\s*#' .env | grep -v '^\s*$' | xargs)

# 激活 Python venv（如果存在）
if [ -d .venv ]; then
    source .venv/bin/activate
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Daily English 管线开始..."

python3 scripts/daily_pipeline.py "$@"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Daily English 管线完成"
