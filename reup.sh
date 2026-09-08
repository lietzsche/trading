#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$ROOT_DIR/.quick-tunnels"
URL_FILE="$STATE_DIR/urls.env"

cd "$ROOT_DIR"

is_running() {
  local pid_file="$1" pid
  [[ -f "$pid_file" ]] || return 1
  read -r pid < "$pid_file"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

for service in trade-service admin-server; do
  if ! is_running "$STATE_DIR/$service.pid"; then
    echo "오류: $service Quick Tunnel이 실행 중이 아닙니다." >&2
    echo "먼저 ./up.sh를 실행하세요." >&2
    exit 1
  fi
done

echo "Quick Tunnel은 유지하고 Docker 서비스를 다시 빌드·배포합니다..."
docker compose up -d --build --remove-orphans

echo
echo "재배포가 완료되었습니다. 기존 Quick Tunnel URL은 그대로 유지됩니다."
if [[ -f "$URL_FILE" ]]; then
  # 이 파일은 up.sh가 생성하며 값에는 공백이나 셸 코드가 들어가지 않는다.
  source "$URL_FILE"
  echo "trade-service: ${TRADE_SERVICE_URL:-확인 불가}"
  echo "admin-server:  ${ADMIN_SERVER_URL:-확인 불가}"
else
  echo "URL 파일을 찾지 못했습니다: $URL_FILE" >&2
fi
