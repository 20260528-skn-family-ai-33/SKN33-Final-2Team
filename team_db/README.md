# team_db — 팀 DB 전체 백업을 넣는 곳

이 폴더의 백업 파일은 Git에 올리지 않아요(`.gitignore`). 이 안내 파일만 올라가요.

## 현재 기본: #124 공유 BGE DB

`growpath_bge_m3_embedding.dump`(36,077,485바이트, SHA-256 `d96c16ceeca8f8d6de8015d2f40903b9f7d6ccecddc8fc33f1e7213bd2a48c4b`)와 동반 manifest를 이 폴더에 둡니다. 저장소 루트에서 `docker compose up -d --wait db` 후 `./scripts/restore-bge-db.ps1 -Apply`로 **별도 `growpath_bge_m3`**에 복원합니다. 도구는 이름·크기·해시·모델 계약을 확인하고 기존 DB 덮어쓰기를 거부합니다. 동일 백업 재실행은 DB를 바꾸지 않습니다.

현재 앱의 `GP5_APP_DB_NAME`은 이 BGE DB입니다. 기존 `growpath` OpenAI DB와 백업은 보존하며 `down -v`로 볼륨을 지우지 않습니다. [전체 검색 연결·모델 준비·재실행 안내](../backend/README.md#공유-bge-m3-db-연결-124)를 따릅니다. BGE는 2026-11-06 로컬 스냅샷, 기존 Drive OpenAI 공유본은 2026-11-04이므로 모델만 다른 동일 데이터로 비교하지 않습니다.

## 백업 사용 기준

현재 코드가 복원·사용하는 백업은 위 BGE 공유본뿐입니다. 이전 백업 복원 서비스·환경변수·스크립트는 제거했습니다. `.env`에는 앱과 DB 서비스의 공통 이름 `GP5_APP_DB_NAME=growpath_bge_m3`를 사용합니다. 실제 이전 백업·DB 데이터는 코드 정리와 별개이며 자동 삭제하지 않습니다.

## 규정 원문 PDF (`regulations/`)

관리자 화면 '규정 데이터'에서 지금 규정을 PDF로 내려받을 때 쓰는 원문이에요. 이것도 Git에 올리지 않아요.

- 넣을 것: 팀 DB 자료의 `data/regulations/한국수자원공사_규정_통합전처리_V01/source/` 폴더를 통째로 `team_db/regulations/source/` 로 복사 (PDF 28개 · 약 26MB)
- 팀 DB의 `regulations.regulation_files.storage_key`(`source/…/….pdf`)가 이 폴더 기준 경로예요. 백엔드는 이 폴더를 읽기 전용으로 붙여요(`docker-compose.yml`).
- 없으면 목록은 보이고 '원문 없음'으로 표시돼요. 다른 곳에 두었다면 `.env`의 `GP5_REGULATION_FILES_DIR`에 그 위치를 적어요(로컬 파이썬 실행 때).

팀 DB 자료 폴더를 통째로 주고받지 마세요. 그 폴더에는 팀원의 실제 `.env`(키·비밀번호)가 들어 있을 수 있어요. 백업 파일 하나만 받으면 돼요.
