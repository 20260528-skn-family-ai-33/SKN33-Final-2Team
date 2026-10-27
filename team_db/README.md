# team_db — 팀 DB 전체 백업을 넣는 곳

이 폴더의 백업 파일은 Git에 올리지 않아요(`.gitignore`). 이 안내 파일만 올라가요.

- 넣을 파일: `growpath_latest.dump` (2026-10-27 최신판 · #22 · pg_dump custom 형식 · 36,343,649바이트). 직원·부서·보유 스킬·자격·학력이 모두 이 백업에 들어 있어요(따로 받는 직원 엑셀 없음).
- 받는 곳: 팀 산출물 드라이브의 `데이터 수집 및 저장 › DB` 폴더(DB 담당). 크기·SHA-256은 `database/data/exports/growpath_latest.manifest.json`과 같아야 해요.
- 넣은 뒤: 저장소 맨 위에서 `docker compose up -d --build` → DB가 비어 있을 때만 이 파일로 복원해요.
- 이름이 다른 백업을 쓰려면 `.env`의 `TEAM_DB_FILE`을 그 이름으로 고쳐요.

## 규정 원문 PDF (`regulations/`)

관리자 화면 '규정 데이터'에서 지금 규정을 PDF로 내려받을 때 쓰는 원문이에요. 이것도 Git에 올리지 않아요.

- 넣을 것: 팀 DB 자료의 `data/regulations/한국수자원공사_규정_통합전처리_V01/source/` 폴더를 통째로 `team_db/regulations/source/` 로 복사 (PDF 28개 · 약 26MB)
- 팀 DB의 `regulations.regulation_files.storage_key`(`source/…/….pdf`)가 이 폴더 기준 경로예요. 백엔드는 이 폴더를 읽기 전용으로 붙여요(`docker-compose.yml`).
- 없으면 목록은 보이고 '원문 없음'으로 표시돼요. 다른 곳에 두었다면 `.env`의 `GP5_REGULATION_FILES_DIR`에 그 위치를 적어요(로컬 파이썬 실행 때).

팀 DB 자료 폴더를 통째로 주고받지 마세요. 그 폴더에는 팀원의 실제 `.env`(키·비밀번호)가 들어 있을 수 있어요. 백업 파일 하나만 받으면 돼요.
