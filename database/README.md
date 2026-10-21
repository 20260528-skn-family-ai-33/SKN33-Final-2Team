# DB 코드와 실행 안내

PostgreSQL 스키마·마이그레이션, 공식 자료 수집·스킬 매핑, 규정/자료 벡터 검색, 업무 저장 API, 전체 백업/복원 도구다. 2026-10-21 전달 구현을 등록한 것으로 목업의 인증·화면·에이전트 통합 완료를 뜻하지 않는다.

## 설치

팀 저장소 루트에서 Python 3.12 가상환경을 만든다. `requirements.lock.txt`는 이관 검사에 사용한 Windows/Python 3.12의 전체 의존성 버전이다.

```powershell
python -m venv .venv-db
.\.venv-db\Scripts\python.exe -m pip install -r database/requirements.txt
.\.venv-db\Scripts\python.exe -m pip check
```

`database/.env.example`을 `database/.env.local`로 복사하고 본인의 접속 정보를 넣는다. `SUPABASE_DB_URL`이라는 이름은 기존 코드 호환용이며 로컬 PostgreSQL에도 사용한다. 실제 설정은 Git에 넣지 않는다.

DB가 없어도 도움말과 아래 단위 검사를 실행할 수 있다.

```powershell
cd database
..\.venv-db\Scripts\python.exe scripts/db.py --help
..\.venv-db\Scripts\python.exe scripts/restore_db.py --help
..\.venv-db\Scripts\python.exe load_data.py --help
..\.venv-db\Scripts\python.exe scripts/check_import.py
..\.venv-db\Scripts\python.exe -m unittest tests.test_db_deployment tests.test_catalog_expansion tests.test_regulation_vectors tests.test_import_package -v
```

`tests.test_canonical_database`는 실제 복원 DB가 필요한 검사다. 단위 검사 통과를 실제 복원·권한 검증으로 해석하지 않는다. 정확한 이관 검사 결과는 [산출물 대응표](../docs/07_데이터베이스_저장소_설계/README.md)에 기록한다.

## 데이터와 실행

전체 덤프·직원 seed·규정 원본·확장 바이너리는 Git에 없다. [외부 자료 manifest](assets.manifest.json)의 버전/해시와 [복원 안내](RESTORE.md)를 따른다. 외부 공유 위치는 아직 미지정이므로 자료 입수 전 실제 복원은 할 수 없다.

복원한 DB를 연결한 뒤 상태를 확인한다.

```powershell
python scripts/db.py verify
python -m src.database.vectors.resource_vectors status
python -m src.database.vectors.regulation_vectors status
```

`load_data.py --dry-run`은 외부 자료 API를 호출하지만 적재·임베딩은 하지 않는다. 기본 적재 경로, 벡터 `embed`, 규정 `search`는 유료 OpenAI API를 호출할 수 있으므로 예산·권한 안에서 명시적으로 실행한다. 이관 검증에서는 호출하지 않았다.

## 구현과 산출물

| 처리 | 주요 구현 | 설명·근거 |
|---|---|---|
| 구조·마이그레이션 | `src/database/migrations/`, `final_schema.py`, `catalog.current.json` | [DB 설계·ERD·현재 구조](../docs/07_데이터베이스_저장소_설계/README.md) |
| 수집·정제·매핑 | `src/database/ingestion/`, `src/shared/` | [전처리 결과서와 코드](../docs/08_데이터_전처리_결과서/README.md) |
| 임베딩·검색 | `src/database/vectors/` | [벡터DB 결과서와 코드](../docs/09_벡터DB_구축_결과서/README.md) |
| 업무 저장 | `app_store.py`, `db_client.py` | DB 설계의 업무 관계·알려진 미완료 항목 |
| 전체 백업·복원 | `portable.py`, `scripts/restore_db.py` | [외부 자료·복원 절차](RESTORE.md) |

[import-manifest.json](import-manifest.json)은 원본 커밋·파일 해시와 이관 변경 이유를 기록한다. [snapshot-audit.json](snapshot-audit.json)은 전달 백업에 수행한 정적 검사다. 전달자의 실행 기록과 이번 직접 검사를 구분한다.

`src/db/`는 이전 명령 호환용이며 새 사용 경로는 `src/database/`다. 적용된 마이그레이션은 재작성하지 않는다. 직원 초기 데이터는 별도 검토하며 공용 기본 비밀번호를 배포하지 않는다.

ERD는 등록된 HTML 전체를 템플릿으로 사용한다. `python -m src.database.erd --template ../docs/07_데이터베이스_저장소_설계/ERD_최종.html`로 실제 DB의 스키마·건수를 읽어 갱신할 수 있다(`database/` 기준). 화살표·표 배치·드래그·검색 기능을 유지하고 내장 JSON만 바꾼다. 이 명령은 실제 DB 연결이 필요하며 이관 검증에서는 실행하지 않았다. Drive 문서 3종의 동일성·관리 시트의 이전 링크는 [산출물 대응표](../docs/07_데이터베이스_저장소_설계/README.md)에 기록했다.
