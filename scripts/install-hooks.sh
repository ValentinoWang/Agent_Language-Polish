#!/usr/bin/env bash
# 安装 git pre-push 钩子: 推送前自动跑快速档本地 CI(CI_FAST=1)。
# 用法: bash scripts/install-hooks.sh
set -euo pipefail
cd "$(dirname "$0")/.."
HOOK=.git/hooks/pre-push
cat > "$HOOK" << 'INNER'
#!/usr/bin/env bash
echo "[pre-push] running local CI (fast mode)..."
CI_FAST=1 bash scripts/ci.sh
INNER
chmod +x "$HOOK"
echo "installed $HOOK (CI_FAST=1 scripts/ci.sh)"
