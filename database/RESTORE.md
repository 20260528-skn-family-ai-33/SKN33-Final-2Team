# 외부 DB 자료와 복원 · 2026-10-29

최신 공유본은 `growpath_latest.dump`와 같은 위치의 `growpath_latest.manifest.json`이다. 덤프 SHA-256 `beb9ac646a746434979f889f6fd564608534477b4e85c2f2e78dd95008285373`, 38,297,980바이트다. 강좌 시간·커리큘럼(025·026), 가상 직원 100명 보완, REAL_USER 4명의 데모 업무/프로젝트, `gpt-6-luna`로 생성한 목표 후보 12개를 포함한다. 제외 요청한 직원 1명은 바꾸지 않았다.

[공유 폴더](https://drive.google.com/drive/folders/1DyJ67R5bYMEwKF-PChdOcxGF8TCNtPsx)에서 두 파일을 받는다. 기존 링크와 공유 권한을 유지했으며 업로드 후 다시 내려받아 두 파일의 SHA-256을 대조했다. [외부 자료 manifest](assets.manifest.json)와 [실제 생성 기록](data/exports/actual_goal_preload_20261029.manifest.json)에 버전·검증을 연결했다. 원문·개인 입력·덤프·비밀키는 Git에 넣지 않는다.

## 새 DB 복원

Python 3.12, PostgreSQL 17, pgvector가 필요하다. 검증 환경은 PostgreSQL 17.11·pgvector 0.8.2 Windows였다. 설치는 [README](README.md)를 따른다. 가상환경을 활성화한 뒤 `database/`에서 실행한다.

```powershell
python scripts/restore_db.py restore --archive "<외부 백업 폴더>/growpath_latest.dump" --initialize --write-config --port 55435 --pg-bin "C:/실제_PostgreSQL_설치/bin"
python scripts/db.py migrate
python scripts/db.py verify
python -m src.database.vectors.resource_vectors status
```

비밀번호는 출력되지 않는 터미널 입력을 사용한다. 기존 DB·데이터 디렉터리·`.env.local`은 덮어쓰지 않는다. 기존 서버라면 `--initialize`를 생략하고 비어 있는 새 DB 이름을 지정한다. 포트가 사용 중이면 점유자를 먼저 확인한다. 설치 바이너리와 서버 확장은 별도로 준비한다. 복원에는 OpenAI 키나 유료 API 호출이 필요 없다.

이번 전체 덤프는 기준 스키마 **53표·22,418행**과 기존 앱 보조 스키마 `app_ext` **25표·24행**, 합계 **78표·22,442행**이다. 기준 표 구조/ERD는 바꾸지 않았으며 정적 ERD의 건수는 강좌 checkpoint 22,300행이다. `inventory`는 기존 복원 도구와 호환되는 기준 53표이며, 전체 78표 지문은 manifest의 `all_schema_table_fingerprints`에 따로 기록한다. 기본 복원 도구는 기준 inventory를 대조하고, 작성 PC의 이번 추가 검사는 전체 78표와 실제 로그인 API까지 검증했다.

목표 후보는 `public.employee_recommended_prompts`, 이유·근거는 `app_ext.goal_suggestion_meta`, 입력 해시·상태는 `app_ext.goal_suggestion_runs`에 있다. `public`만 복원하면 사전 로딩 상태가 누락되므로 **전체 덤프를 복원한다**. 복원본에서 4명 각각 3회 재로그인·세션 조회·목표 화면 진입 시 기존 후보를 재사용하고 추가 모델 호출 0회를 확인했다. 새 업무/프로젝트 저장 계약과 자동 갱신에는 PR #29의 백엔드·프런트 배포도 필요하다.

앱 추가 준비가 필요하면 `backend/tools/setup_db.py --supplement-only --keep-team-passwords`를 사용해 기존 직원 암호를 보존한다. 준비 도구는 저장된 목표 생성 상태가 있으면 초기 가데이터 후보로 덮지 않는다. API 키·직원 사번/암호·관리자 계정 설정은 저장소 밖에서 관리한다. 수신 PC의 실제 실행·배포는 아직 검증하지 않았다.

013~020 원본 SQL이 없어 빈 DB를 SQL만으로 재구성하거나 구판 10/21 DB에 021·022만 적용하는 방식은 지원하지 않는다. 최신 백업의 001~026 이력을 검증하고 이미 적용한 SQL의 바이트·해시를 바꾸지 않는다. 024의 조회 정책은 본인 또는 같은 기관·같은 부서의 부서장에게만 허용하며 부서 상하 관계는 사용하지 않는다.

## 백업·되돌리기

```powershell
python scripts/restore_db.py backup --output "<외부 백업 폴더>/growpath_새버전.dump"
```

백업 도구는 `app_ext`를 포함한 모든 스키마를 덤프하지만 기본 inventory는 기준 53표다. 공유 전 앱 보조 표의 후보/이유/입력 해시를 별도로 확인한다. 복구는 검증된 이전 전체 백업을 새 DB에 복원·검사한 뒤 연결을 전환한다. 이후 사용자 입력이 있으면 먼저 보존·대조한다. PostgreSQL 내부 파일이나 다른 PC의 `.venv`를 실행 환경으로 복사하지 않는다.

시간·커리큘럼만 포함한 앞선 checkpoint는 `growpath_curriculum_20261028.dump` SHA-256 `c401c1f60e0b7d2e513dce031225cc2dad0d879ec22674900608b55c31d2c48c`이며 로컬 원본을 보존한다. 최신 Drive 파일에는 그 내용과 이후 인사/목표 작업이 함께 들어 있다. 중간 인사·실제 생성 전 백업의 해시는 각각의 외부 자료 manifest를 따른다.
