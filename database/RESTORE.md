# 외부 DB 자료와 복원 · 2026-10-27

최신 기준은 `growpath_latest.dump`와 같은 위치의 `growpath_latest.manifest.json`이다. SHA-256 `be3648e42907cd566d9716354437665260ccb3c26041a0dcdcb20e13db643189`, 36,345,626바이트, 53테이블·22,298행·227개 제약조건이다. 별도 새 DB 복원에서 전체 53개 표 지문과 벡터 연산 일치를 확인했다. 10/21 백업은 역사 기록으로 보존하며 현재 복원 기준과 구분한다.

[공유 폴더](https://drive.google.com/drive/folders/1DyJ67R5bYMEwKF-PChdOcxGF8TCNtPsx)의 두 파일을 받는다. [외부 자료 manifest](assets.manifest.json)에 최신 덤프 링크와 해시를 연결했다. 입수한 파일을 SHA-256으로 대조한다. 직원 seed·기본 비밀번호·실제 `.env`·회사/생활안내 원문·수집 상세·벡터·실행 DB는 Git에 없다. 실제 키나 비밀번호가 포함된 ZIP을 배포하지 않는다.

## 새 환경

Python 3.12, PostgreSQL 17, pgvector가 필요하다. 검증 환경은 PostgreSQL 17.11·pgvector 0.8.2 Windows였다. 설치는 [README](README.md)를 따른다. 가상환경을 활성화한 뒤 `database/`에서 실행한다.

```powershell
python scripts/restore_db.py restore --archive "<외부 백업 폴더>/growpath_latest.dump" --initialize --write-config --port 55435 --pg-bin "C:/실제_PostgreSQL_설치/bin"
python scripts/db.py migrate
python scripts/db.py verify
python -m src.database.vectors.resource_vectors status
```

비밀번호는 출력되지 않는 터미널 입력을 사용한다. 기존 DB·데이터 디렉터리·`.env.local`은 덮어쓰지 않는다. 기존 서버라면 `--initialize`를 생략하고 비어 있는 새 DB 이름을 지정한다. 포트가 사용 중이면 먼저 점유자를 확인한다. 설치 바이너리와 서버 확장은 별도로 준비한다.

복원 도구는 포트를 지정할 수 있지만 `import_knowledge.py`, `supplement_courses.py`, `supplement_course_catalog.py`, `correct_course_skills.py`, `verify_course_catalog.py`, `verify_course_expansion_live.py`는 승인된 최종 DB인 `127.0.0.1:55435/growpath`로 대상을 제한한다. 다른 포트·DB 이름으로 복원했다면 이 도구들은 거절한다. 일부 도구는 현재 작업 폴더의 로컬 클러스터 경로도 확인하므로 연결 설정만 바꿔 제한을 우회하지 않는다.

013~020 SQL이 없어 빈 DB를 SQL만으로 재구성하거나 구판 10/21 DB에 021·022만 적용하는 방식은 지원하지 않는다. 최신 백업의 001~024 이력을 검증한다. 과거 적용 SQL을 수정해 이력을 맞추지 않는다. 팀원 작성 REAL_USER 5명의 실제 사번·소속·학력과 작성된 스킬·프로필이 최신 백업에 포함된다. 사번 필수 제약은 원본의 NOT VALID 상태를 유지하며 현재 누락 행은 0개다. 최신 023 DB에는 024만, 최신 022 DB에는 023·024를 적용한다.

## 백업·되돌리기

```powershell
python scripts/restore_db.py backup --output "<외부 백업 폴더>/growpath_새버전.dump"
```

동일 스냅샷의 전체 덤프와 manifest를 생성한다. 되돌릴 때는 검증된 이전 백업을 새 DB에 복원해 검사한 뒤 연결을 전환한다. 현재 입력이 추가됐다면 먼저 보존한다. PostgreSQL 내부 파일이나 다른 PC의 `.venv`를 복사해 실행 환경으로 사용하지 않는다. 복원은 OpenAI API가 필요 없다.

024 이전 백업은 담당자가 보관한 SHA-256 `4558b33e5f12bf41a9d78f45311cb108d4e558c88d5b9e045328af2f2d5e4106`이며 REAL_USER 작성값을 포함한다. 복구 시 이전 전체 백업을 새 DB에 복원하고 연결을 전환한다. 024는 본인 또는 같은 기관·같은 부서의 부서장만 조회를 허용한다. 부서 상하 관계는 권한에 사용하지 않는다. 원본·증빙 묶음은 [assets.manifest.json](assets.manifest.json)에 해시를 연결했다. 10/28 작성 PC의 복제 DB에서 실제 인증 API 계약 8개를 확인했으며 저장 위치와 재실행법은 [DB 안내](README.md)를 따른다. 앱의 `app_ext` 보조 표는 이 53개 표 백업과 별도로 초기화·백업해야 한다. 수신 PC의 실제 실행·배포·모델 통합은 미검증이다.
