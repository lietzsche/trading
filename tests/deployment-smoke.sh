#!/usr/bin/env bash
# Exercise down.sh against a disposable copy and mocked Docker only.
# No real Docker resources, Quick Tunnels, or repository state are touched.
set -Eeuo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_DIR="$(mktemp -d /tmp/trading-deploy-test.XXXXXX)"
trap 'rmdir "$TASK_DIR"' EXIT
cp "$REPO_DIR/down.sh" "$TASK_DIR/down.sh"

docker() {
  case "$*" in
    'compose down --volumes --remove-orphans') return 0 ;;
    'volume inspect 001_postgres_data') return 1 ;;
    *) echo "Unexpected Docker command in test" >&2; return 2 ;;
  esac
}
export -f docker
mkdir "$TASK_DIR/.quick-tunnels"
touch "$TASK_DIR/.runtime.env"
env -u BASH_ENV bash --noprofile --norc "$TASK_DIR/down.sh"
test ! -e "$TASK_DIR/.quick-tunnels"
test ! -e "$TASK_DIR/.runtime.env"
rm "$TASK_DIR/down.sh"
echo "Deployment cleanup smoke test passed (Docker mocked)."
