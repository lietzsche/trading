#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$ROOT_DIR/.quick-tunnels"

cd "$ROOT_DIR"

stop_tunnel() {
  local service="$1" pid_file="$STATE_DIR/$service.pid" pid args
  [[ -f "$pid_file" ]] || return 0
  read -r pid < "$pid_file"

  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    if [[ "$args" == *cloudflared* && "$args" == *tunnel* ]]; then
      echo "$service Quick Tunnel을 종료합니다..."
      kill "$pid"
      for _ in {1..10}; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
      done
      if kill -0 "$pid" 2>/dev/null; then
        echo "경고: 정상 종료되지 않아 $service 터널을 강제 종료합니다." >&2
        kill -KILL "$pid" 2>/dev/null || true
      fi
    else
      echo "경고: PID $pid 프로세스가 cloudflared가 아니어서 종료하지 않았습니다." >&2
    fi
  fi
}

stop_tunnel trade-service
# 이전 구성에서 실행된 admin-server 터널도 함께 정리한다.
stop_tunnel admin-server

echo "Docker Compose 리소스를 종료·정리합니다..."
docker compose down --volumes --remove-orphans

# 이전 버전에서 external로 생성했거나 Compose 관리 라벨이 없는 경우까지
# 빠짐없이 정리하기 위해 명시적으로 한 번 더 확인한다.
if docker volume inspect 001_postgres_data >/dev/null 2>&1; then
  echo "PostgreSQL 데이터 볼륨(001_postgres_data)을 삭제합니다..."
  docker volume rm 001_postgres_data
fi

rm -rf -- "$STATE_DIR"

echo "정리가 완료되었습니다. 컨테이너, 네트워크, Quick Tunnel, 관련 볼륨을 모두 삭제했습니다."
