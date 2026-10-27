# DB 코드와 실행 안내 · 2026-10-27

최종 DB의 직원 입력 저장, 회사 정보·생활안내 검색, 강좌 확충·스킬 보정과 ERD를 팀 코드로 연결한다. 실제 데이터는 외부 백업으로 전달하며 이 저장소에 넣지 않는다. 화면·챗봇의 실제 통합 완료와 구분한다.

## 현재 기준과 반영 내용

| 항목 | 기준 |
|---|---:|
| 테이블 / FK / 적용 이력 | 53 / 87 / 22 |
| 강좌·모듈 / 추천 가능 | 2,060 / 2,045 |
| 강좌 스킬 연결 / 자료·스킬 벡터 | 3,658 / 2,469 |
| 회사 정보 / 생활안내 검색 조각 | 137 / 305 |

- `021_employee_input_compatibility.sql`: 기존 직원 테이블을 유지하며 `employee_input_profiles`에 경험·프로젝트·교육·선호를 저장한다. `employee_form.py`의 미리보기는 롤백하고 `--apply`에서만 배치를 저장한다.
- `022_knowledge_documents.sql`: 문서 4개와 조각 442개를 별도 `knowledge` 영역에 저장한다. `knowledge_documents.py`는 범주를 강제하고 `knowledge_search.py`는 키워드·벡터 혼합 검색과 본사/인재개발원 구분을 지원한다. 원문 위치와 가상 자료 여부를 함께 반환한다.
- `catalog_scope.py`, `course_sources.py`, `instructional_content.py`: 공식 출처·원본 ID·가격·모집기간·공개 목차를 확인하고 선수지식·강사 경력을 학습 스킬과 구분한다. Hadoop 단독 DW 연결, Python/비동기·웹 프레임워크 등의 과대 매칭을 보정한다. 필터 버전은 `kr-it-2026-10-27-v7`이다.
- `supplement_course_catalog.py`: 기존 자료를 초기화하지 않는 강좌 추가 경로다. 신규 1,889개 반영과 후속 17개 강좌의 연결 8개 제거·11개 추가는 외부 최신 백업에 포함된다. 심사 입력·전후 링크·원문은 외부 증빙으로 보존한다.
- `course_skill_corrections.py`: 검토된 원문 해시·전후 링크를 검사하고 지정한 연결과 실제 벡터를 한 트랜잭션으로 갱신한다. 임의 해시 변경으로 최신 벡터처럼 표시하지 않는다.
- [최신 ERD](../docs/07_데이터베이스_저장소_설계/ERD_최종.html): 기존 양식에서 회사 정보 문서 위·검색 조각 아래로 별도 영역을 정렬한다. 다른 표의 저장 배치는 유지한다.

건수는 2026-10-27 검증 시점이다. 추천 여부는 현재 날짜·출처 신선도에 따라 다시 판정하며, 실제 수강 종료 여부와 수강신청 상태는 구분한다. MS Learn은 영상이 아닌 학습 모듈이다.

## 설치와 무료 검사

팀 저장소 루트에서 Python 3.12 환경을 만든다. 의존성은 기존 고정 버전을 유지했다.

```powershell
python -m venv .venv-db
.\.venv-db\Scripts\python.exe -m pip install -r database/requirements.txt
.\.venv-db\Scripts\python.exe -m pip check
cd database
..\.venv-db\Scripts\python.exe scripts/check_import.py
..\.venv-db\Scripts\python.exe scripts/check_workspace.py
```

`check_import.py`는 파일 해시·현재 스키마·ERD·외부 백업 manifest를 대조하며 DB/API를 호출하지 않는다. `check_workspace.py`도 기본은 무료 단위 검사다. PR #22 후속 보완 후 단위 182개 실행·통과, 5개 건너뜀(외부 규정 원문 4개·DB 클래스 1개), 별도 복제 DB 통합 33개 실행·통과를 확인했다. 회귀 검사는 직원 참조·외부 ID 보존, 같은 ID 재적재, 롤백, 동시 쓰기 차단, 증분 갱신 후 로드맵 자료 보존과 두 사용자의 실행 모드별 자료 연결·결과 보고를 다룬다.

재적재 검사의 AI 심사·임베딩은 모의 처리하고 SQL·FK는 실제 PostgreSQL에서 실행했다. 새 실행 모드 검사는 수집·적재·백업 생성을 모의 처리하며 초기화 SQL은 실제 복제 DB의 외부 롤백 트랜잭션에서 실행했다. 원본 53개 테이블의 전후 지문은 같고 복제 DB는 제거했다. 모의 HTTP 503 재시도 출력은 예상한 검사다. 실제 API·GPU 비용은 이번 Git 준비와 보완에서 사용하지 않았다.

복원 DB가 있을 때 `scripts/check_workspace.py --integration`은 소유한 로컬 DB를 복제해 검사한 뒤 복제본만 제거한다. 실제 직원 표에 검사용 행을 쓰지 않는다. 검사 결과는 Git에서 제외되는 `migration_work/`에 남긴다.

## 복원과 설정

`database/.env.example`을 비공개 `.env.local`로 복사해 본인 설정을 입력한다. 개인 설정·직원 seed·런타임·덤프·원문·벡터는 Git에 없다. [복원 안내](RESTORE.md)와 [외부 자료 manifest](assets.manifest.json)를 따른다. 공유 위치가 미지정인 자료는 담당자에게 받아야 한다.

중요: 013~020 원본 SQL은 제공되지 않았다. 10/21 DB에 021·022만 적용해 최신 구조로 바꾸는 방식은 지원하지 않는다. 최신 전체 스냅샷을 **새 DB**에 복원한 뒤 `migrate`·`verify`를 실행한다. 과거 001~012 SQL과 013~020의 기록된 해시는 보존한다.

```powershell
python scripts/db.py --help
python scripts/restore_db.py --help
python scripts/employee_form.py --help
python scripts/import_knowledge.py --help
python scripts/supplement_course_catalog.py --help
python scripts/correct_course_skills.py --help
```

직원 입력은 비공개 JSON으로 전달한다. 문서·강좌 적재와 보정의 입력·검토 증빙도 외부 자료다. `--apply`, 벡터 `embed`, 문서 질문 검색은 실제 DB 변경 또는 유료 API 호출을 수행할 수 있으므로 합의한 범위를 확인하고 실행한다. 최신 백업 확인에는 위 무료 검사와 `verify`를 사용한다.

`python load_data.py`의 기본 실행은 증분 갱신이며 기존 `--incremental`도 같은 동작을 유지한다. 초기화하려면 별도 `--reset`을 지정해야 한다. 라이브러리의 `execute_full_pipeline()`과 기존 `ingest_and_map_all()`도 기본은 증분 갱신이다. 기존에 옵션 없이 초기화하던 자동 실행은 목적을 확인해 `--reset`을 명시해야 한다.

`python load_data.py --dry-run`은 **DB 저장·초기화·임베딩만 생략하며 수집 과정의 GPT 심사 비용은 발생한다.** `--reset --dry-run`도 초기화를 실행하지 않는다. 일반 적재와 dry-run 모두 합의된 API 사용 범위에서 실행한다. 강좌 보충 도구의 `--apply` 없는 무료 준비 검사, `check_workspace.py` 기본 검사와 구분한다.

`--reset` 초기화는 직원이 참조하는 직무·보유 자격·학력 전공의 행과 외부 원본 ID 연결을 보존한다. 재수집에서 통과하지 않은 보존 행은 `scope_excluded`로 두고 신규 추천에서 제외한다. 초기화 중 참조가 추가돼 누락되지 않도록 관련 직원 표의 쓰기를 잠근다. 초기화는 기존 로드맵의 자료 연결·스킬 매핑·벡터를 지우므로 최신 백업을 확인한 뒤 실행한다. 자동 전체 백업을 먼저 만들지만 초기화는 수집 전에 별도로 커밋된다. 이후 수집·적재가 실패해도 초기화가 자동 복구되지는 않는다. 성공·실패 보고의 `reset.removed_resource_associations`, `user_data_changed`, `backup`으로 실제 연결 삭제와 복구 경로를 확인한다. 라이브러리는 초기화 후 예외를 `PipelineExecutionError.report`로 전달하며 CLI의 `--report`에도 같은 내용을 저장한다.

증분 갱신의 최종 검사는 이용 기간·출처 유효기간이 지난 자료의 추천 상태와 검색 인덱스만 정리한다. 기존 자료 행과 저장된 로드맵의 자료 연결은 보존한다. K-MOOC 날짜는 Unix 초·밀리초를 모두 해석한다. 강좌 추가 시 기존 NULL·공백 URL은 URL 중복 비교에서 제외하되 ID 중복 검사와 신규 URL 필수 검사는 유지한다. 이 보완에는 스키마 변경이나 새 마이그레이션이 필요하지 않다.

규정 검색의 검토 대기 결과는 기본 제외다. 필요할 때 `regulation_vectors.search(..., include_review=True)` 또는 `python -m src.database.vectors.regulation_vectors search --query "질문" --include-review`로 명시한다. 미사용 설정 `REGULATION_RAG_INCLUDE_REVIEW`는 예제에서 제거했다. 실제 질문 검색은 유료 임베딩을 사용할 수 있다.

## ERD·산출물·호환성

```powershell
python -m src.database.erd
```

기본 템플릿은 `database/docs/erd_template.html`, 출력은 `docs/07_데이터베이스_저장소_설계/ERD_최종.html`이다. 과거 `--template`의 완성 HTML 방식과 `render_html()`도 유지한다. [구조 목록](../docs/07_데이터베이스_저장소_설계/SCHEMA.md)·[스키마 SQL](../docs/07_데이터베이스_저장소_설계/schema_final.sql)과 함께 본다. 화면 제어는 Chrome 현재 URL 확인 실패로 중단돼 새 기타 영역의 화면 검증은 미완료다. 표 포함·중복·FK·저장 위치 적용 조건은 정적으로 확인했다.

ERD 파일 출력은 현재 산출물과 같은 CRLF로 명시해 운영체제별 개행 차이를 방지한다. 기존 완성 HTML과 저장된 53개 테이블 메타데이터를 다시 넣은 출력이 원본 바이트와 동일함을 확인했다. 이번 보완은 화면 내용·배치를 변경하지 않는다.

[DB 설계 대응표](../docs/07_데이터베이스_저장소_설계/README.md), [전처리 대응표](../docs/08_데이터_전처리_결과서/README.md), [벡터 검색 대응표](../docs/09_벡터DB_구축_결과서/README.md)에 구현을 연결했다. Word/PDF 제출 원본은 이번 준비에서 수정하지 않았다. 과거 Drive 일치 기록은 10/21 시점의 기록이며 현재 Drive 재대조 완료로 해석하지 않는다.

[import-manifest.json](import-manifest.json)은 원래 출처·해시와 이번 로컬 최종본의 파일 해시를 구분한다. [snapshot-audit.json](snapshot-audit.json)은 과거 정적 검사와 최신 복원·보정 검증을 구분한다. `src/db/` 호환 경로와 비밀값 미출력·외부 직원 seed 사전 거절 동작을 유지한다.

남은 검토: 근거가 약한 MLOps 10건, 강사 경력으로 OS 보안에 연결된 KMOOC_7204의 CI/CD 재분류, 사번이 없는 기존 REAL_USER 5명의 실제 사번 확인, 실제 추천 화면·챗봇 연동·다른 PC 실행·사람 리뷰. #14의 선택 벡터 갱신 작업과 #15의 권한·활동·코멘트 계약은 별도 작업이며 이번 준비로 완료 처리하지 않는다.
