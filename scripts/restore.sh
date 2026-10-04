#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
force=false
if [[ "${1:-}" == --force ]]; then force=true; shift; fi
[[ $# == 1 && -f "$1" ]] || { echo '사용법: scripts/restore.sh [--force] 백업.dump' >&2; exit 1; }
dump="$1"
if "$force"; then
  [[ -t 0 ]] || { echo '운영 복원은 대화형 터미널에서만 허용됩니다.' >&2; exit 1; }
  echo '경고: 운영 DB 데이터를 덮어씁니다. 먼저 API/자동매매를 중지하고 새 백업을 만드세요.' >&2
  read -r -p '운영 덮어쓰기를 승인하려면 RESTORE 입력: ' confirmation
  [[ "$confirmation" == RESTORE ]] || exit 1
  docker compose exec -T postgres sh -c 'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error --single-transaction' < "$dump"
  exit
fi
# Only this generated database may be removed by the cleanup trap.
verification_db="trading_restore_check_$(date +%s)_${RANDOM}"
cleanup() { docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$1"' sh "$verification_db"; }
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$verification_db"
trap cleanup EXIT
docker compose exec -T postgres sh -c 'exec pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --exit-on-error --single-transaction' sh "$verification_db" < "$dump"
echo '임시 DB 복원 완료. 백업 시점의 주요 테이블 행 수:'
docker compose exec -T postgres sh -c 'exec psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -c "SELECT '\''tb_user'\'' AS table_name,count(*) FROM tb_user UNION ALL SELECT '\''tb_upbit_key'\'',count(*) FROM tb_upbit_key UNION ALL SELECT '\''upbit'\'',count(*) FROM upbit UNION ALL SELECT '\''upbit_order_history'\'',count(*) FROM upbit_order_history UNION ALL SELECT '\''ai_analyses'\'',count(*) FROM ai_analyses;"' sh "$verification_db"
