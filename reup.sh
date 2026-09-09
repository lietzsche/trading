#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$ROOT_DIR/.quick-tunnels"
URL_FILE="$STATE_DIR/urls.env"
RUNTIME_ENV="$ROOT_DIR/.runtime.env"
WAIT_SECONDS="${TUNNEL_WAIT_SECONDS:-60}"

cd "$ROOT_DIR"

is_running() {
  local pid_file="$1" pid
  [[ -f "$pid_file" ]] || return 1
  read -r pid < "$pid_file"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

if ! is_running "$STATE_DIR/api-service.pid"; then
  echo "오류: api-service Quick Tunnel이 실행 중이 아닙니다." >&2
  echo "먼저 ./up.sh를 실행하세요." >&2
  exit 1
fi

if [[ ! -s "$RUNTIME_ENV" ]]; then
  umask 077
  printf 'SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" > "$RUNTIME_ENV"
fi

echo "Quick Tunnel은 유지하고 Docker 서비스를 다시 빌드·배포합니다..."
# Python 주문 스케줄러와 Java 주문 스케줄러가 겹치지 않도록 이전
# trade-service 컨테이너를 먼저 정지한 후 새 구성을 시작한다.
if docker container inspect 001-trade-service-1 >/dev/null 2>&1; then
  echo "기존 Java trade-service를 먼저 종료합니다..."
  docker stop 001-trade-service-1 >/dev/null
fi
docker compose up -d --build --remove-orphans
docker compose wait db-migrate

start_tunnel() {
  local service="$1" port="$2"
  local log_file="$STATE_DIR/$service.log" pid_file="$STATE_DIR/$service.pid"
  echo "$service Quick Tunnel을 시작합니다 (localhost:$port)..." >&2
  nohup setsid cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$port" </dev/null >"$log_file" 2>&1 &
  local pid=$! url="" elapsed=0
  printf '%s\n' "$pid" > "$pid_file"
  while (( elapsed < WAIT_SECONDS )); do
    url="$(grep -Eo 'https://[A-Za-z0-9-]+\.trycloudflare\.com' "$log_file" 2>/dev/null | head -n 1 || true)"
    if [[ -n "$url" ]] && curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      printf '%s\n' "$url"
      return 0
    fi
    kill -0 "$pid" 2>/dev/null || { echo "오류: $service Quick Tunnel이 종료되었습니다." >&2; rm -f "$pid_file"; return 1; }
    sleep 1
    ((elapsed += 1))
  done
  echo "오류: ${WAIT_SECONDS}초 안에 $service HTTPS 응답을 확인하지 못했습니다." >&2
  kill "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  return 1
}

stop_legacy_trade_tunnel() {
  local pid_file="$STATE_DIR/trade-service.pid" pid args
  [[ -f "$pid_file" ]] || return 0
  read -r pid < "$pid_file"
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    if [[ "$args" == *cloudflared* && "$args" == *tunnel* ]]; then
      echo "기존 Java Quick Tunnel을 종료합니다..."
      kill "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$pid_file" "$STATE_DIR/trade-service.log"
}

API_SERVICE_URL=""
if [[ -f "$URL_FILE" ]]; then
  source "$URL_FILE"
fi
stop_legacy_trade_tunnel
echo
echo "재배포가 완료되었습니다. 기존 Quick Tunnel URL은 그대로 유지됩니다."
if [[ -n "${API_SERVICE_URL:-}" ]]; then
  printf 'API_SERVICE_URL=%s\n' "$API_SERVICE_URL" > "$URL_FILE"
  echo "Trading React/FastAPI: $API_SERVICE_URL"
else
  echo "URL 파일을 찾지 못했습니다: $URL_FILE" >&2
fi
