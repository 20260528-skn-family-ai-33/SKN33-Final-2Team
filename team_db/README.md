# team_db — 팀 DB 전체 백업을 넣는 곳

이 폴더의 백업 파일은 Git에 올리지 않아요(`.gitignore`). 이 안내 파일만 올라가요.

## 현재 기본: #124 공유 BGE DB

`growpath_bge_m3_embedding.dump`(2026-11-09판, 36,082,540바이트, SHA-256 `ed693fe99054ccac2811c3a7d62f21ee10b0500e2c58be43ed73d0a600c9c178`)와 동반 manifest를 이 폴더에 둡니다. 저장소 루트에서 `docker compose up -d --wait db` 후 `./scripts/restore-bge-db.ps1 -Apply`로 **별도 `growpath_bge_m3`**에 복원합니다. 도구는 이름·크기·해시·모델 계약을 확인하고 기존 DB 덮어쓰기를 거부합니다. 동일 백업 재실행은 DB를 바꾸지 않습니다.

현재 앱의 `GP5_APP_DB_NAME`은 이 BGE DB입니다. 기존 `growpath` OpenAI DB와 백업은 보존하며 `down -v`로 볼륨을 지우지 않습니다. [전체 검색 연결·모델 준비·재실행 안내](../backend/README.md#공유-bge-m3-db-연결-124)를 따릅니다. BGE 공유본은 2026-11-07판에 알림 규칙·결과 보고서 과제 표를 더한 2026-11-09판이고, 기존 Drive OpenAI 공유본은 2026-11-04이므로 모델만 다른 동일 데이터로 비교하지 않습니다.

## 새 공유본으로 교체

복원 도구는 해시가 다른 기존 DB를 덮어쓰지 않으므로, 이미 `growpath_bge_m3`를 복원한 PC는 그 DB만 지우고 다시 복원합니다. 파일을 넣고 Compose를 다시 올리는 것만으로는 DB가 바뀌지 않고, 시작 검사도 옛 DB를 통과시킵니다. 각자 로컬에서 만든 로드맵·보고서는 사라지고 다시 로그인해야 합니다.

새 파일 두 개를 이 폴더에 덮어쓴 뒤 저장소 루트의 PowerShell에서 실행합니다.

```powershell
git switch main
git pull --ff-only origin main
docker compose down
docker compose up -d --wait db
docker compose exec -T db dropdb -U growpath growpath_bge_m3
powershell -ExecutionPolicy Bypass -File scripts/restore-bge-db.ps1 -Apply
docker compose up -d --build
```

- `docker compose down`을 먼저 실행합니다. 앱이 DB에 연결된 채로는 `dropdb`가 실패합니다.
- `down -v`는 쓰지 않습니다. 같은 볼륨의 기존 OpenAI DB까지 지워집니다.
- `.env`에서 `GP5_DB_USER`를 바꿨다면 `-U`에 그 값을 씁니다.
- 2026-11-09판에는 `backend/db/migrate_notification_rules.sql`과 `migrate_report_tasks.sql`이 이미 적용돼 있어 따로 실행하지 않습니다.

## 백업 사용 기준

현재 코드가 복원·사용하는 백업은 위 BGE 공유본뿐입니다. 이전 백업 복원 서비스·환경변수·스크립트는 제거했습니다. `.env`에는 앱과 DB 서비스의 공통 이름 `GP5_APP_DB_NAME=growpath_bge_m3`를 사용합니다. 실제 이전 백업·DB 데이터는 코드 정리와 별개이며 자동 삭제하지 않습니다.

## 규정 원문 PDF (`regulations/`)

관리자 화면 '규정 데이터'에서 지금 규정을 PDF로 내려받을 때 쓰는 원문이에요. 이것도 Git에 올리지 않아요.

- 넣을 것: 팀 DB 자료의 `data/regulations/한국수자원공사_규정_통합전처리_V01/source/` 폴더를 통째로 `team_db/regulations/source/` 로 복사 (PDF 28개 · 약 26MB)
- 팀 DB의 `regulations.regulation_files.storage_key`(`source/…/….pdf`)가 이 폴더 기준 경로예요. 백엔드는 이 폴더를 읽기 전용으로 붙여요(`docker-compose.yml`).
- 없으면 목록은 보이고 '원문 없음'으로 표시돼요. 다른 곳에 두었다면 `.env`의 `GP5_REGULATION_FILES_DIR`에 그 위치를 적어요(로컬 파이썬 실행 때).

팀 DB 자료 폴더를 통째로 주고받지 마세요. 그 폴더에는 팀원의 실제 `.env`(키·비밀번호)가 들어 있을 수 있어요. 백업 파일 하나만 받으면 돼요.
