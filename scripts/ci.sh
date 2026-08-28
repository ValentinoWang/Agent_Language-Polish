#!/usr/bin/env bash
# =============================================================================
# StyleOS 本地 CI —— 质量门禁的唯一事实源
# -----------------------------------------------------------------------------
# 本项目的常规门禁在本地执行（合并前跑本脚本），不依赖云端 Actions 分钟数。
# .github/workflows/ci.yml 仅保留 workflow_dispatch 手动入口，且复用本脚本，
# 保证"本地与云端跑的是同一套检查"。
#
# 用法:
#   bash scripts/ci.sh              # 完整门禁: lint + 测试/覆盖率 + pack lint
#                                   #           + schema export + skill build + uv build
#   CI_FAST=1 bash scripts/ci.sh    # 快速档(pre-push 钩子用): lint + 测试, 跳过构建
#   CI_DOCKER=1 bash scripts/ci.sh  # 追加 docker 镜像构建(默认跳过)
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

FAST="${CI_FAST:-0}"
WITH_DOCKER="${CI_DOCKER:-0}"

step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

step "uv sync (dev+mcp)"
uv sync --extra dev --extra mcp --quiet

step "ruff check"
uv run ruff check src tests

if [ "$FAST" = "1" ]; then
  step "pytest (fast)"
  uv run pytest -q
else
  step "pytest + coverage (fail_under=75)"
  uv run pytest --cov=styleos --cov-report=term-missing
fi

step "styleos pack lint"
uv run styleos pack lint

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

step "schema export (code-first drift check)"
uv run styleos schema-export --output "$TMP/schemas"

step "skill build (pack compile check)"
uv run styleos pack build --output "$TMP/skills"

if [ "$FAST" != "1" ]; then
  step "uv build (wheel/sdist)"
  uv build --out-dir "$TMP/dist" >/dev/null 2>&1 && ls "$TMP/dist"
fi

if [ "$WITH_DOCKER" = "1" ]; then
  step "docker build"
  docker build -t styleos-ci .
fi

step "LOCAL CI: ALL GREEN"
