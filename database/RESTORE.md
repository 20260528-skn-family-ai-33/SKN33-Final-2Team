# 외부 DB 자료와 복원 · 2026-10-27

최신 기준은 `growpath_latest.dump`와 같은 위치의 `growpath_latest.manifest.json`이다. SHA-256 `9ce26041c5bf95ea9e6ad88c5ea8d3817e3c6097e7e85c0f99512123098001fb`, 36,343,649바이트, 53테이블·22,284행·227개 제약조건이다. 별도 새 DB 복원에서 전체 53개 표 지문과 벡터 연산 일치를 확인했다. 10/21 백업은 역사 기록으로 보존하며 현재 복원 기준과 구분한다.

[외부 자료 manifest](assets.manifest.json)의 공유 위치는 미지정이다. 입수한 파일을 SHA-256으로 대조한다. 직원 seed·기본 비밀번호·실제 `.env`·회사/생활안내 원문·수집 상세·벡터·실행 DB는 Git에 없다. 실제 키나 비밀번호가 포함된 ZIP을 배포하지 않는다.

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

013~020 SQL이 없어 빈 DB를 SQL만으로 재구성하거나 구판 10/21 DB에 021·022만 적용하는 방식은 지원하지 않는다. 최신 백업의 001~022 이력을 검증한다. 001~012·021·022 SQL을 수정해 이력을 맞추지 않는다. 기존 REAL_USER 5명의 사번 누락은 전달 스냅샷의 알려진 경고이며 값을 임의 생성하지 않는다.

## 백업·되돌리기

```powershell
python scripts/restore_db.py backup --output "<외부 백업 폴더>/growpath_새버전.dump"
```

동일 스냅샷의 전체 덤프와 manifest를 생성한다. 되돌릴 때는 검증된 이전 백업을 새 DB에 복원해 검사한 뒤 연결을 전환한다. 현재 입력이 추가됐다면 먼저 보존한다. PostgreSQL 내부 파일이나 다른 PC의 `.venv`를 복사해 실행 환경으로 사용하지 않는다. 복원은 OpenAI API가 필요 없다.

최신 백업 이전판은 `growpath_latest_before_skill_correction_20261027.dump`다. 원본·증빙 묶음은 [assets.manifest.json](assets.manifest.json)에 해시를 연결했다. 수신 PC의 실제 실행과 앱 연동은 미검증이다.
