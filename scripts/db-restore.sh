#!/bin/sh
# 빈 DB일 때만 팀 DB 전체 백업을 복원한다(docker compose 의 db-restore 서비스가 실행).
# 이미 public 스키마에 표가 있으면 아무것도 하지 않는다 → 여러 번 켜도 같은 결과.
set -eu
n=$(psql -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")
if [ "$n" != "0" ]; then
  echo "DB에 이미 표가 ${n}개 있어 복원은 건너뜀"
  exit 0
fi
f="/dump/${TEAM_DB_FILE}"
if [ ! -f "$f" ]; then
  echo "팀 DB 백업 파일이 없어요: team_db/${TEAM_DB_FILE}"
  echo "  팀 DB 담당 팀원에게 받아 team_db/ 에 넣고 다시 실행하세요(이름이 다르면 .env 의 TEAM_DB_FILE 을 고침)."
  ls /dump 2>/dev/null | sed 's/^/  team_db 에 있는 파일: /' || true
  exit 1
fi
echo "팀 DB 백업 복원: ${TEAM_DB_FILE}"
pg_restore --no-owner --no-privileges --exit-on-error -d "$PGDATABASE" "$f"
echo "복원 완료"
