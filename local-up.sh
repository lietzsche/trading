#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
if [[ ! -s .env ]]; then
  umask 077
  printf 'POSTGRES_USER=bion_user\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=postgres\n' \
    "$(openssl rand -hex 32)" > .env
  echo "강한 로컬 DB 비밀번호로 .env를 생성했습니다."
fi
if [[ ! -s .runtime.env ]]; then
  umask 077
  printf 'SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" > .runtime.env
fi
SESSION_COOKIE_SECURE=false SIGNUP_ENABLED=true docker compose up -d --build --wait --wait-timeout 180
echo "MA40 Auto Trader: http://localhost:8001"
echo "첫 계정 생성 후 SIGNUP_ENABLED=false로 다시 실행하는 것을 권장합니다."
