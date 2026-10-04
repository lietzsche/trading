#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
umask 077
mkdir -p backups
exec 9>backups/.backup.lock
flock -n 9 || { echo '다른 백업이 진행 중입니다.' >&2; exit 1; }
target="backups/$(TZ=Asia/Seoul date +%Y%m%d-%H%M).dump"
[[ ! -e "$target" ]] || { echo '같은 분의 백업이 이미 있습니다.' >&2; exit 1; }
temporary="$(mktemp backups/.pending.XXXXXX)"
trap 'rm -f -- "$temporary"' EXIT
docker compose exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$temporary"
[[ -s "$temporary" ]] || { echo '백업 파일이 비어 있습니다.' >&2; exit 1; }
chmod 600 "$temporary"
mv -- "$temporary" "$target"
mapfile -t dumps < <(find backups -maxdepth 1 -type f -regextype posix-extended -regex 'backups/[0-9]{8}-[0-9]{4}\.dump' | sort -r)
for ((index=14;index<${#dumps[@]};index++)); do rm -- "${dumps[index]}"; done
printf '백업 완료: %s (최근 14개 유지)\n' "$target"
