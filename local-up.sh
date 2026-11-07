#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
[[ -s .env ]] || { echo "오류: cp .env.example .env 후 POSTGRES_PASSWORD를 설정하세요." >&2; exit 1; }
if [[ ! -s .runtime.env ]]; then
  umask 077
  printf 'SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" > .runtime.env
fi
SESSION_COOKIE_SECURE=false SIGNUP_ENABLED=true docker compose up -d --build --wait --wait-timeout 180
echo "MA40 Auto Trader: http://localhost:8001"
echo "첫 계정 생성 후 SIGNUP_ENABLED=false로 다시 실행하는 것을 권장합니다."
