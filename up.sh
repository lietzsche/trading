#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$ROOT_DIR/.quick-tunnels"
URL_FILE="$STATE_DIR/urls.env"
WAIT_SECONDS="${TUNNEL_WAIT_SECONDS:-60}"
RUNTIME_ENV="$ROOT_DIR/.runtime.env"

cd "$ROOT_DIR"

command -v docker >/dev/null 2>&1 || { echo "오류: docker를 찾을 수 없습니다." >&2; exit 1; }
command -v cloudflared >/dev/null 2>&1 || { echo "오류: cloudflared를 찾을 수 없습니다." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "오류: Docker Compose v2가 필요합니다." >&2; exit 1; }

mkdir -p "$STATE_DIR"

if [[ ! -s "$RUNTIME_ENV" ]]; then
  umask 077
  printf 'SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" > "$RUNTIME_ENV"
fi

# 이전 Java 구성의 터널이 남아 있으면 외부 URL을 하나만 유지하기 위해 종료한다.
if [[ -f "$STATE_DIR/trade-service.pid" ]]; then
  read -r legacy_pid < "$STATE_DIR/trade-service.pid"
  if [[ "$legacy_pid" =~ ^[0-9]+$ ]] && kill -0 "$legacy_pid" 2>/dev/null; then
    legacy_args="$(ps -p "$legacy_pid" -o args= 2>/dev/null || true)"
    [[ "$legacy_args" == *cloudflared*tunnel* ]] && kill "$legacy_pid" 2>/dev/null || true
  fi
  rm -f "$STATE_DIR/trade-service.pid" "$STATE_DIR/trade-service.log"
fi

is_running() {
  local pid_file="$1" pid
  [[ -f "$pid_file" ]] || return 1
  read -r pid < "$pid_file"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

for service in api-service; do
  if is_running "$STATE_DIR/$service.pid"; then
    echo "오류: $service Quick Tunnel이 이미 실행 중입니다." >&2
    echo "재배포는 ./reup.sh, 전체 재시작은 ./down.sh 후 ./up.sh를 사용하세요." >&2
    exit 1
  fi
done

rm -f "$URL_FILE" "$STATE_DIR"/*.pid "$STATE_DIR"/*.log

echo "Docker 서비스를 빌드하고 시작합니다..."
docker compose up -d --build
docker compose wait db-migrate

start_tunnel() {
  local service="$1" port="$2"
  local log_file="$STATE_DIR/$service.log"
  local pid_file="$STATE_DIR/$service.pid"

  echo "$service Quick Tunnel을 시작합니다 (localhost:$port)..." >&2
  nohup setsid cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$port" \
    </dev/null >"$log_file" 2>&1 &
  local pid=$!
  printf '%s\n' "$pid" > "$pid_file"

  local url="" elapsed=0
  while (( elapsed < WAIT_SECONDS )); do
    if url="$(grep -Eo 'https://[A-Za-z0-9-]+\.trycloudflare\.com' "$log_file" 2>/dev/null | head -n 1)" && [[ -n "$url" ]]; then
      if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
        printf '%s\n' "$url"
        return 0
      fi
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "오류: $service Quick Tunnel이 종료되었습니다. 로그: $log_file" >&2
      return 1
    fi
    sleep 1
    ((elapsed += 1))
  done

  echo "오류: ${WAIT_SECONDS}초 안에 $service HTTPS 응답을 확인하지 못했습니다. 로그: $log_file" >&2
  kill "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  return 1
}

cleanup_started_tunnels() {
  local pid_file pid
  for pid_file in "$STATE_DIR"/*.pid; do
    [[ -f "$pid_file" ]] || continue
    read -r pid < "$pid_file"
    [[ "$pid" =~ ^[0-9]+$ ]] && kill "$pid" 2>/dev/null || true
  done
}

trap cleanup_started_tunnels ERR INT TERM
API_SERVICE_URL="$(start_tunnel api-service 8001)"
trap - ERR INT TERM

cat > "$URL_FILE" <<EOF
API_SERVICE_URL=$API_SERVICE_URL
EOF

echo
echo "배포가 완료되었습니다."
echo "Trading React/FastAPI: $API_SERVICE_URL"
echo "URL 저장 위치: $URL_FILE"
echo "다시 확인: sed -n 's/^[^=]*=//p' '$URL_FILE'"
