# DB 코드와 실행 안내 · 2026-10-29

최종 DB의 직원 입력 저장, 회사 정보·생활안내 검색, 강좌 확충·스킬 보정과 ERD를 팀 코드로 연결한다. 실제 데이터는 외부 백업으로 전달하며 이 저장소에 넣지 않는다. 화면·챗봇의 실제 통합 완료와 구분한다.

## 현재 기준과 반영 내용

| 항목 | 기준 |
|---|---:|
| 테이블 / FK / 시간·목차 반영 백업 적용 이력 | 53 / 87 / 26 |
| 강좌·모듈 / 추천 가능 | 2,060 / 2,045 |
| 강좌 스킬 연결 / 자료·스킬 벡터 | 3,658 / 2,469 |
| 회사 정보 / 생활안내 검색 조각 | 137 / 305 |

- `021_employee_input_compatibility.sql`: 기존 직원 테이블을 유지하며 `employee_input_profiles`에 경험·프로젝트·교육·선호를 저장한다. `employee_form.py`의 미리보기는 롤백하고 `--apply`에서만 배치를 저장한다.
- `022_knowledge_documents.sql`: 문서 4개와 조각 442개를 별도 `knowledge` 영역에 저장한다. `knowledge_documents.py`는 범주를 강제하고 `knowledge_search.py`는 키워드·벡터 혼합 검색과 본사/인재개발원 구분을 지원한다. 원문 위치와 가상 자료 여부를 함께 반환한다.
- `023_direct_department_visibility.sql`: 직원 조회 공통 함수 추가 이력이며 현재 정책은 024가 대체한다. 팀원 작성 REAL_USER 5명의 사번·소속·학력·스킬·입력 프로필은 최신 외부 백업에 반영했다. 원문과 개인정보는 Git에 넣지 않는다.
- `024_same_department_visibility.sql`: 본인 또는 같은 기관·같은 부서의 부서장만 직원·로드맵 조회를 허용한다. 부서 상하 관계는 조회 권한에 사용하지 않는다.
- `025_course_duration.sql`: 제공처 총시간·영상/학습 구분과 별도 계획 추정·근거를 저장한다.
- `026_course_curriculum.sql`: 공개 목차·소개 정규화 결과·출처 해시를 저장하고 원문과 벡터 입력을 보존한다.
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

024 최종 검증: 단위 183개 실행·통과(5개 제외), 실제 격리 DB 통합 37개 실행·통과(사번 누락 계정이 없어 3개 제외). 권한 검사 7개에서 직원·프로젝트 각 100개 조합, 같은 부서 허용·다른 부서장 차단, 역할·소속 변경, 코멘트·진행 조회, 본인 전용 수정, 023→024 전환·반복 적용·롤백을 확인했다. 원본 DB는 검사 중 변경하지 않았고 실제 024 적용은 이력 외 52개 표의 지문을 보존했다. 최종 전체 백업 복원에서도 53개 표와 벡터·함수가 일치했다.

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

### 부서장 조회 범위와 연결 계약 (#15)

`public.employee_can_read_employee(actor integer, target integer)`는 본인 또는 같은 기관·같은 `department_id`의 부서장에게만 조회를 허용한다. 일반 직원은 본인만 조회한다. 다른 부서의 직원·부서장은 조직상 위치와 무관하게 제외한다. 부서 미지정 직원도 본인은 조회할 수 있다. `employee_can_read_project(actor integer, target uuid)`는 프로젝트 소유자에 같은 규칙을 적용한다. 직원 소속이나 저장 데이터는 바꾸지 않는다.

같은 부서 부서장은 팀원의 로드맵 진행을 조회하고 기존 코멘트 기능을 사용한다. 다른 사람의 로드맵 수정과 상세 입력폼 조회는 계속 허용하지 않는다. 부서 이동·부서장 해제 즉시 현재 소속과 역할로 다시 검사하며 부서 트리 변경은 권한에 영향을 주지 않는다.

직원 기본 프로필을 읽는 `get_employee_profile(employee_id, *, actor_employee_id=...)`는 이제 인증된 요청자 ID가 필수다. 목록은 `list_visible_employee_profiles(*, actor_employee_id=...)`를 쓴다. 누락·잘못된 ID는 저장소 조회 전에 거절하고, 범위 밖 단건은 `ValueError`를 반환한다. 서버가 로그인 세션에서 actor를 정해야 하며 브라우저가 보낸 actor 값을 그대로 신뢰하면 안 된다. 기존 호출자는 023·024 적용 후 인증 actor를 전달하도록 함께 바꿔야 한다. 코멘트 작성 트리거와 로드맵 진행 조회도 새 프로젝트 함수에 따른다.

`list_test_users()`와 `.table()`은 신뢰된 개발·운영 코드용 저수준 인터페이스다. 이 함수 변경이 PostgreSQL 관리자 직접 SQL을 제한하거나 모든 앱 경로에 RLS를 추가하지는 않는다. 아래의 실제 HTTP 계약 검사와 관리 화면·수신 PC·모델 통합 검증은 구분한다.

최신 023 DB는 `python scripts/db.py migrate`로 024만 적용하고 `verify`로 확인한다. 최신 022 DB는 023·024를 순서대로 적용한다. 그 이전 구판은 최신 전체 백업을 새 DB에 복원한다. 기존 001~023 적용 SQL은 수정하지 않았다. 복구는 024 적용 전 검증 백업을 새 DB에 복원한 뒤 연결을 전환하며 그 사이 추가된 입력은 먼저 보존한다. 권한 회귀 검사는 `tests/test_department_access.py`에서 수행한다.

2026-10-28에 [PR #24](https://github.com/20260528-skn-family-ai-33/SKN33-Final-2Team/pull/24)가 병합된 최신 `main`의 `9d5164c`를 `fix/15-direct-manager-scope`에 반영했다. README·검사 실행기·manifest의 충돌을 조정해 #14의 선택 벡터 갱신 검사와 #15의 권한·인증 API 검사를 함께 유지한다. 앱의 같은 부서 범위 구현을 재사용한다.

기존 Docker DB는 백업 파일을 교체해도 자동으로 복원되지 않으므로 현재 DB 버전에 맞는 마이그레이션 또는 새 DB 복원 절차를 사용한다. DB 권한 적용과 API 입력 검증 코드 배포도 각각 필요하다. Git 전달과 사람 리뷰·병합·배포는 각각의 기록으로 확인한다.

## 앱 저장 계약 대조 · 이슈 #15

최신 전체 백업을 임시 PostgreSQL DB에 복원하고 `backend/db/02_app_ext.sql`로 앱 보조 표를 생성해 검사했다. 원본 직원 DB를 테스트 대상으로 사용하지 않았다. 아래는 현행 구현의 계약이며 새로운 보존 정책을 합의한 기록은 아니다.

| 범위 | 저장 위치와 확인한 동작 |
|---|---|
| 인증·공개 범위 | `app_ext.sessions`의 인증 세션을 사용한다. 같은 기관·같은 부서 부서장만 팀원 로드맵을 조회한다. 상위 부서장·다른 기관·일반 동료는 제외하며 소속/역할 변경은 기존 세션에도 즉시 적용된다. 다른 직원 수정은 허용하지 않는다. |
| 개인 입력 | 경험·개발 연수·기술·프로젝트·교육은 `public.employee_input_profiles`, 자격은 `employee_certifications`와 `employees.unlisted_certifications`. 업무 설명·없음 확인·처음 값 복원 정보는 `app_ext.employee_self_inputs`. 본인 저장·재시도·복구와 오류 시 기존 값 보존을 확인했다. |
| 평정 동의·철회 | `app_ext.employee_evaluations`의 기본값·현재 덮어쓰기 값·변경 시각. 기본값과 같으면 `consent=NULL`로 기본값을 따른다. 누적 동의 이력·정책 버전은 현재 저장하지 않는다. 문자열 `"false"`/누락/NULL/숫자를 422로 거절하도록 수정했다. |
| 학습 조건 | 작성 중에는 `public.projects.draft_choices.draft.prefs`, 확정 후에는 `roadmaps.content.prefs`와 `app_ext.roadmap_versions.plan.prefs`. 조건 수정·재조회·타인 수정 거절을 확인했다. |
| 진행·증빙 | `(roadmap_id, activity_id)`로 `app_ext.activity_progress`에 상태·메모·첨부 메타데이터를 upsert하며 `roadmap_steps.is_completed`와 같은 트랜잭션에서 저장한다. 첨부 파일 실물은 앱 파일 저장소에서 별도 관리한다. 부서장 응답에는 메모·첨부를 제외한다. |
| 수정안·이력 | `app_ext.roadmap_revisions`, `roadmap_meta`, `roadmap_versions`와 현재 `public.roadmaps.content`. 같은 수정안의 동시 확정은 200/409로 나뉘고 버전은 한 번만 늘어난다. 최초 `baseline_content`, 버전 1과 기존 활동 ID의 진행 기록을 보존한다. |
| 코멘트 | 본문은 `public.roadmap_comments`, 확인·반영 상태는 `app_ext.comment_meta`. 선택한 코멘트만 `applied_version`에 연결한다. 기존 `modification_completed_at` 일괄 시각을 채택/반영 여부로 해석하지 않는다. 이미 반영한 의견의 수정은 409다. |

개발 연수에 숫자로 바꿀 수 없는 입력이 오면 500 대신 422를 반환하도록 보완했다. 현재 프런트엔드는 동의값을 boolean으로 보내므로 정상 호출 형식은 유지한다. 오류 계약은 [API 계약](../frontend/docs/API_계약.md)에 연결했다.

10/28 PR #24 동기화 후 검사 결과는 단위 193개 통과·5개 제외, 격리 DB 통합 50개 통과·3개 제외다. 통합 검사에는 `tests/test_app_contracts.py`의 실제 인증 HTTP 검사 8개와 #14의 선택 벡터 갱신 검사 5개가 포함된다. 3개 제외는 사번 누락 계정이 현재 없기 때문이다. LLM·임베딩·목표 생성 작업은 호출하지 않았으며 SQL·FK·세션·라우터는 실제 구현을 사용했다. 검사 전후 원본 DB 53개 표의 지문이 같고 검사용 복제본은 제거했다.

```powershell
# 저장소 루트에서 앱 검사 의존성 추가 설치
python -m pip install -r backend/requirements.txt
cd database
python scripts/check_workspace.py --integration --app-contracts
```

통합 실행기는 소유한 로컬 DB/클러스터 경로를 검사해 임시 복제본을 만들고 앱 보조 표는 그 복제본에만 생성한다. 원본에 사용자가 접속 중이어서 template 복제가 거절되면 검증된 덤프를 `growpath_employee_form_test_`로 시작하는 별도 로컬 DB에 복원한 뒤 비공개 `EMPLOYEE_FORM_TEST_DB_URL`을 지정하고 `python -m unittest tests.test_app_contracts -v`로 HTTP 검사만 실행할 수 있다. 실행 후 직접 만든 복제본은 직접 정리한다.

사용 측 검토: 현재 동의 덮어쓰기/변경 시각만으로 요구사항을 충족하는지, 누적 동의 이력·보존 기간이 필요한지는 담당자 확인이 남아 있다. 관리자 화면 전체·수신 PC·모델 생성 품질·배포 완료는 이번 검사 범위가 아니다. 정책 결정을 대신해 추가 표를 만들지 않았다. SQL 023·024 적용 후 이 DB API 계약을 배포하며 기존 `.get_employee_profile()` 호출자는 인증 actor를 전달해야 한다.

```powershell
python -m src.database.erd
```

기본 템플릿은 `database/docs/erd_template.html`, 출력은 `docs/07_데이터베이스_저장소_설계/ERD_최종.html`이다. 과거 `--template`의 완성 HTML 방식과 `render_html()`도 유지한다. [구조 목록](../docs/07_데이터베이스_저장소_설계/SCHEMA.md)·[스키마 SQL](../docs/07_데이터베이스_저장소_설계/schema_final.sql)과 함께 본다. 화면 제어는 Chrome 현재 URL 확인 실패로 중단돼 새 기타 영역의 화면 검증은 미완료다. 표 포함·중복·FK·저장 위치 적용 조건은 정적으로 확인했다.

ERD 파일 출력은 현재 산출물과 같은 CRLF로 명시해 운영체제별 개행 차이를 방지한다. 기존 완성 HTML과 저장된 53개 테이블 메타데이터를 다시 넣은 출력이 원본 바이트와 동일함을 확인했다. 이번 보완은 화면 내용·배치를 변경하지 않는다.

[DB 설계 대응표](../docs/07_데이터베이스_저장소_설계/README.md), [전처리 대응표](../docs/08_데이터_전처리_결과서/README.md), [벡터 검색 대응표](../docs/09_벡터DB_구축_결과서/README.md)에 구현을 연결했다. Word/PDF 제출 원본은 이번 준비에서 수정하지 않았다. 과거 Drive 일치 기록은 10/21 시점의 기록이며 현재 Drive 재대조 완료로 해석하지 않는다.

[import-manifest.json](import-manifest.json)은 원래 출처·해시와 이번 로컬 최종본의 파일 해시를 구분한다. [snapshot-audit.json](snapshot-audit.json)은 과거 정적 검사와 최신 복원·보정 검증을 구분한다. `src/db/` 호환 경로와 비밀값 미출력·외부 직원 seed 사전 거절 동작을 유지한다.

남은 검토: 근거가 약한 MLOps 10건, 강사 경력으로 OS 보안에 연결된 KMOOC_7204의 CI/CD 재분류, 실제 추천 화면·챗봇·관리 화면 전체·다른 PC 실행·사용 측 사람 리뷰. #14의 선택 벡터 갱신 기능은 PR #24로 병합됐다. #15는 위 저장 계약 확인과 코드 반영·리뷰·병합을 구분한다.

## 강좌 시간·계획 시간 · 이슈 #26

전체 2,060개 중 제공처 총시간 확보 1,730개, 미확보 330개다. 모든 강좌에 양수의 로드맵 계산 시간을 마련했다.

| 출처 | 전체 | 총시간 확보 | 총시간 미확보·계획 추정 |
|---|---:|---:|---:|
| 인프런 | 1,144 | 1,141 | 3 |
| K-MOOC | 161 | 161 | 0 |
| Microsoft Learn | 292 | 292 | 0 |
| STEP | 136 | 136 | 0 |
| KOCW | 310 | 0 | 310 |
| 생활코딩 | 17 | 0 | 17 |

`courses.duration_seconds`는 제공처 총시간(초), `duration_kind`는 영상/학습 구분이다. `estimated_duration_seconds`는 총시간 미확보 시 별도 계획 추정이며 `duration_provenance`에 필드·단위·수집 시각·원본 해시와 추정 산식을 남긴다. 두 시간은 실제 수강자의 이수시간 측정값이 아니다.

- 인프런은 전체 영상 차시의 runtime 초를 합산하며 비영상 자료는 제외한다. 영상 시간이 빠진 3개는 확인된 합계에 **같은 강좌에서 확인한 영상 길이의 중앙값**을 누락 영상 수만큼 더한다. 일괄 20분을 적용하지 않으며 총시간 확보로 세지 않는다. [공식 예시](https://www.inflearn.com/course/유니티-심화-과정?cid=113593)의 10시간 9분과 원본 합계 36,540초를 대조했다.
- K-MOOC는 `course_playtime` 초 단위 학습시간을 사용한다. 0/미기재면 확인된 `vod_playtime`을 영상시간으로 사용한다. 영상과 학습시간은 구분한다. [공식 예시](https://www.kmooc.kr/view/course/detail/10301).
- Microsoft Learn은 공식 `duration_in_minutes`를 초로 변환한다. [공식 API 필드 설명](https://learn.microsoft.com/en-us/training/support/catalog-api-developer-reference).
- STEP은 `edutime`의 시간 단위를 변환한다. [공식 예시](https://www.step.or.kr/dtyCrsDetailForm.do?crscd=1024&crsseqId=233831&dgrId=1695&dgrSeCd=03&verCd=201600604_16v6)의 학습시간 20시간을 대조했다.
- 미확보 KOCW는 **번호가 같은 차시의 영상 조각을 묶은 뒤 차시당 학습 50분**을 가정한다. 번호가 빈 행은 앞선 차시에 포함하고 제공 중단 표기는 제외한다. `KOCW_1422415`는 80개 영상을 7개 차시로 묶어 66시간 40분 대신 5시간 50분의 계획 추정을 사용한다. 실제 재생시간이 확인된 것은 아니다.
- 생활코딩은 전체 목차 항목당 학습·실습 20분의 초기 계획 가정을 유지한다. 실측으로 보정된 수치는 아니다. 저장된 2~3개 확인용 샘플을 전체 목차로 세지 않으며, 해시가 일치하는 원본 HTML의 전체 목차를 사용한다. 목차도 미확보인 신규 자료에만 초기 계획 2시간을 명시한다. 현재 330개에는 이 최후 가정이 적용된 강좌가 없다.

기존 원본 강좌 필드·스킬·임베딩 입력은 유지했다. 재임베딩/유료 호출은 없다. 관리자 수동 입력 시간은 자동 갱신에서 보존한다. 앱은 확인된 시간 또는 계획 추정을 로드맵 일정에 사용하며 신규 계획에 추정 여부와 근거를 함께 저장한다. 기존 확정 로드맵·버전·진행 기록을 일괄 재작성하지 않는다.

화면은 **10분 단위 반올림**(5분 미만은 ‘10분 미만’)으로 표시하고 DB와 기간 계산은 원래 정밀도를 유지한다. 자료·단계·선택지·간트·실행 기록·수정 화면은 같은 시간 표시 함수를 사용한다. 새로 저장하는 `roadmap_steps.estimated_duration` 문구도 이 규칙을 따르며 `details.hours` 숫자는 반올림하지 않는다. 목록·상세·자료 선택·진단 추천·로드맵 자료에는 플랫폼과 기관/강사를 함께 표시한다. 예: `KOCW · 안양대학교`, `STEP · 현대씨앤알㈜`.

```powershell
# 외부 최신 DB를 복원한 후 database/에서 실행
python scripts/db.py migrate
python scripts/backfill_course_duration.py          # 읽기 전용 미리보기
python scripts/backfill_course_duration.py --apply  # 확인한 원본 시간·계획 추정만 저장
python scripts/backfill_course_curriculum.py        # 읽기 전용 목차 정규화 계획
python scripts/backfill_course_curriculum.py --apply
# 선택: 기존 원본에 없는 공개 목차를 해시 검증한 외부 캐시 manifest로 보충
python scripts/backfill_course_curriculum.py --outline-manifest data/import_sources/curriculum_20261028/manifest.json --apply
```

앱 배포 전 025·026을 적용하고 시간·목차 적재, `backend/db/02_app_ext.sql`, 앱의 자료 보충 단계를 순서대로 실행한다. 새 전체 백업에는 두 마이그레이션과 적재 결과가 포함돼 있다. 시연 계정/목표 재생성 없이 시간만 동기화할 때는 앱 환경에서 `from app.course_time import sync; sync()`를 사용한다. PR #24·#25·#31이 병합된 최신 main `f8b37ed`에 맞췄다. #31은 안내 문서 3개만 바뀌어 검증한 실행 코드는 동일하다. 강좌 PR #32는 병합됐으며 직원 #27은 최신 main `44ef011` 위에 통합해 별도로 검토한다.

검증: Python 단위 213개 통과·5개 제외, 실제 PostgreSQL 시간·목차 검사 3개, 실제 앱 초기화·자료 API·수동 값 보존·일정 계산을 확인했다. 진단·로드맵 모델 호출 직전의 입력 2건을 가로채 소개·목차·추정 여부의 전달을 확인했으며 모델 응답은 고정했다. 프런트 타입 검사·lint·41개 테스트·빌드 통과(lint 기존 경고 37개). 내부 브라우저에서 공개 목차 펼치기·목차 미확보 표시·시간 보정 근거를 확인했다. 유료 모델 HTTP는 차단했으며 실제 모델 생성 품질은 검사하지 않았다. ERD는 메타데이터만 갱신하고 배치는 유지했다.

강좌 PR의 건수는 직원 100명 보완 전의 시간·목차 백업 기준이다. 직원 #27의 코드·데이터 적재는 별도이며 기존 PR #29는 닫힌 상태에서 최신 main 통합·재검증을 준비한다.

최신 로컬 백업은 `growpath_curriculum_20261028.dump`와 [manifest](data/exports/growpath_curriculum_20261028.manifest.json)다. 53테이블·22,300행·26개 적용 이력이며 새 DB로 복원해 53개 표 지문이 모두 일치했다. 이전 시간 반영 백업도 보존한다. 이전 Drive 공유 파일은 덮어쓰지 않았으며 외부 업로드·커밋·푸시·사람 리뷰는 별도다. 복구 시 작업 전 전체 백업을 새 DB에 복원하고 이후 새 입력을 보존한 뒤 연결을 전환한다. 적용된 025·026 SQL을 편집하거나 임베딩 입력 해시만 바꿔 맞추지 않는다.

공개 목차는 2,054개 강좌에서 확보했다(전체 제목이 있는 목차 2,051개, 일부 제목 미제공 3개). 인프런 원본의 제목 없는 15개 항목도 버리지 않고 ‘제목 미제공’으로 표시한다. 생활코딩 17개 전체 목차 318항목과 MS Learn 292개 단원 2,405항목을 저장했다. 기존 목차 누락 111개는 공식 페이지를 무료로 다시 확인했고, K-MOOC 6개 이미지 목차는 Codex가 원본을 읽어 출처 이미지 해시와 전사 방법을 함께 저장했다. 사람 검토로 계산하지 않는다.

K-MOOC `20110`, `20139`, `20140`, `20562`, `20806`, `20808`은 소개·학습 목표만 확보한 `description_only`다. 평가표의 주차 표기를 커리큘럼으로 오인하지 않는다. 이 6개는 화면·모델에 목차 미확보로 전달하고 내용을 생성해 채우지 않는다.

정리된 전체 소개와 공개 목차는 단건 상세 API에서 제공한다. 목록·일괄 조회·로드맵 첨부 응답은 소개 400자와 목차 개수·확보 상태만 보내며, 화면은 상세 진입 시 전체를 별도로 받는다. 목차 없는 강좌·도서·자격증에도 ‘전체 소개·상세 보기’ 링크를 제공한다. 목록 재조회가 이미 받은 상세 캐시를 지우지 않으며, 상세 재진입 시에는 캐시 유무와 관계없이 다시 조회해 관리자 변경을 반영한다. 원문 캐시 없이 복원해도 DB에 저장된 목차를 재사용한다.

AI에는 후보별 제한을 곱하는 대신 **후보 목록 전체의 직렬화된 JSON을 UTF-8 12,000바이트 이하**로 제한한다. 우선 간단한 후보 정보를 유지하고, 최대 4개 강좌에 소개 240자·관련 목차 최대 3항목/240자를 예산 안에서 추가한다. 스킬은 기존처럼 최대 4개다. 기존 로드맵 자료를 우선 보존하며 전체 예산을 넘는 추가 후보는 제외한다. 바이트 제한은 토큰 수가 아니며 시스템 지시·프로필·사용자 입력까지 포함한 전체 문맥의 보장을 뜻하지 않는다. 근거가 없는 후보의 세부 단원은 추정하지 않도록 모델에 명시한다.

10/29 대표 목표 6개×진단/로드맵의 실제 메시지 구조를 로컬 `Qwen/Qwen3.8-27B` 토크나이저와 HF 채팅 템플릿(thinking off)으로 계산했다. 기존 PR 입력 30,394~36,994토큰이 5,412~6,344토큰으로 줄었다. 테스트에서는 출력 4,096토큰을 가정해 16,384문맥 안에 드는지 검사했다. 이는 실제 RunPod 호출이나 배포된 Ollama 템플릿과의 일치 검증이 아니다. 긴 프로필·기획서·심화 답변이 추가되는 운영 입력은 별도 확인해야 한다. 유료 호출은 0회다.

`02_app_ext.sql` 재실행 시 기존 DB에도 `hours_origin` CHECK를 동일하게 추가한다. 이미 잘못된 값이 있으면 적용을 실패시키고 원인을 고치도록 하며 값을 임의로 바꾸지 않는다. 과거 로드맵에 `hoursEstimated`가 없으면 ‘추정 여부 미기록’을 표시하고 저장된 시간은 유지한다. 신규 적재의 최종 검사도 시간·목차를 함께 정규화한다.

관리자가 시간 숫자를 유지한 채 ‘시간 추정’ 표시만 해제해도 `hours_origin=manual`로 저장한다. 이후 시간 동기화가 이 확인값을 덮지 않는다. 시간과 무관한 메모 수정은 확인 처리로 간주하지 않는다. 별도 보충 적재 경로의 정규화와 샘플 목차 캐시 갱신은 이번 선택 수정 범위에서 제외했다.

## 가상 직원 프로필 보완 · 이슈 #27

`TEST_MANUAL` 100명 보완 도구는 부서 업무와 직무·경험·보유 스킬·자격을 연결하며 `REAL_USER`에는 쓰지 않는다. REAL_USER 4명의 업무/프로젝트 데모 입력은 아래의 별도 사용자 승인 작업이다. 전체 계정의 신원·사번·암호·소속·직급·입사/배치일·부서장 권한은 바꾸지 않는다. 부서별 인물 설정은 균형 있는 추천 검증용 가정이며 실제 직원 구성의 통계가 아니다. `submission_note`에 가상 출처·작성 버전·기준일을 기록한다. 기존 학력은 보존하며 전공명이 마스터와 정확히 일치하는 연결만 보정한다.

추가 테이블이나 DDL 마이그레이션은 필요 없다. `scripts/enrich_synthetic_employees.py`와 `src/database/synthetic_employee_profiles.py`가 **외부 검토 계획 → 해시 확인 → 명시적 원자적 적용**의 데이터 변경 절차다. 배포 초기화에서 자동 실행하지 않는다. 실제 인물 자료와 검토 JSON·DB 백업은 Git에 넣지 않고 `data/exports/synthetic_profiles_20261028.manifest.json`으로 버전·해시·집계를 연결한다.

```powershell
# database/에서. 먼저 현재 DB를 백업하고 검토 계획을 저장한다(이 단계는 DB 쓰기 없음).
python scripts/enrich_synthetic_employees.py --as-of 2026-10-28 --output "$env:TEMP/growpath-synthetic-review.json"
# 파일을 검토한 뒤 현재 DB와 차이만 확인한다.
python scripts/enrich_synthetic_employees.py --plan "$env:TEMP/growpath-synthetic-review.json"
# 실제 적용은 검토한 파일 해시를 명시해야 한다.
$profilePlanHash = (Get-FileHash -LiteralPath "$env:TEMP/growpath-synthetic-review.json" -Algorithm SHA256).Hash.ToLowerInvariant()
python scripts/enrich_synthetic_employees.py --plan "$env:TEMP/growpath-synthetic-review.json" --sha256 $profilePlanHash --apply
```

대상 100명이 달라지거나 실제 직원 ID·중복 ID·소유자가 다른 학력·허용하지 않은 필드가 섞이면 거절한다. 계획 이후 값이 바뀐 직원은 덮어쓰지 않고 재검토를 요구한다. SQL 제약 실패는 앞서 저장한 직원까지 전체 롤백한다. 같은 계획의 반복 적용은 0건이다. 기존 개인 학습 선호는 보존한다. 스킬 태그는 경험 분야이며 태그 전체의 숙련 인증을 뜻하지 않으므로 기술별 수행 범위도 함께 읽는다. 프로젝트 독립 수행 이력이 없는 사례는 명시적으로 구분한다.

업무 설명은 기존 `employees.planned_project_description`, 프로젝트는 `employee_input_profiles.project_experience`에서 읽고 쓴다. 새 표/열은 필요 없다. 둘 다 선택이므로 업무만·프로젝트만·둘 다 있는 입력을 지원한다. 업무 설명은 최대 500자이며 빈 값은 NULL이다. 업무만 수정할 때는 빈 입력 프로필을 만들지 않는다. 목표 추천·진단 문항/결과·로드맵에 전달하며 프로젝트 경험은 업로드 기획서와 구분한다. 부서장 응답의 본인 입력 비공개 범위는 유지한다. **DB 적재와 앱 코드 배포가 각각 필요**하다.

무변경 저장은 원래 행과 갱신 시점을 보존한다. 신규 저장은 팀 열을 쓰고 `app_ext.employee_self_inputs`에는 처음 값·입력 상태·업무 설명 변경 해시만 남긴다. 되돌리기는 본인이 고친 처음 설명을 복원하되, 기술만 바꿨거나 이후 관리자가 갱신한 설명은 덮지 않는다. 구판 `edited.workDesc`는 계속 읽으며 명시적 저장 또는 선택 이관 SQL로 옮긴다. `backend/db/migrate_self_work_descriptions.sql`은 충돌 시 전체 롤백하고 구판 사본에 없는 처음 설명을 추정하지 않는다. 원본 DB에 이 선택 SQL을 자동 실행하지 않았다.

로그인·세션 조회는 목표 생성 요청이나 추천 입력 해시 검사를 하지 않는다. 홈페이지에서 본인 입력 저장/되돌리기·평정 동의·관리자 수정/업로드가 성공하면 추천 입력이 바뀐 직원만 갱신한다. 부서명·상위 부서 변경과 보유 자격명 변경도 관련 직원을 포함한다. 목표 화면은 후보가 없는 계정만 처음 준비한다. 동시 요청은 하나의 작업을 공유하고 실패하면 기존 후보를 보존해 수동으로 재시도한다. SQL 직접 수정 후에는 명시적 다시 만들기를 사용한다. 사전 생성·공유 방법은 `backend/README.md`를 따르며 유료 실행은 승인 범위 안에서 수행한다.

사용자 추가 요청으로 REAL_USER 4개 계정에 **데모용 가정**을 반영했다. 업무만 1명·프로젝트만 2명·둘 다 1명이며, 제외 요청한 1명은 모든 기존 값을 보존했다. 기존 스킬/자격·학력·신원·암호·소속·권한은 바꾸지 않았다. 새 프로필 행을 만드는 경우 기존 기술 표시가 사라지지 않도록 보유 기술을 보존했다. 실제 경력/업무 증빙으로 취급하지 않으며 원문은 Git에 넣지 않고 [외부 산출물 manifest](data/exports/real_user_demo_contexts_20261029.manifest.json)로 연결한다. 전체 직원 105명 중 다른 101명과 다른 51개 표 불변을 검증했다. 최신 로컬 백업 `growpath_real_context_20261029.dump`는 53테이블·22,406행이며 Drive에는 아직 업로드하지 않았다.

10/28 기존 검증: 무료 단위 199개 통과·5개 제외, 격리 PostgreSQL 6개, 실제 인증 HTTP 10개 통과. 가상 100명 앱 입력과 6개 직무 목표 모델 입력을 확인했다. 실제 모델 추론은 하지 않았다. 팀원 5명·계정 식별/권한 값·나머지 48개 canonical 표의 불변을 대조했다. `tests.test_synthetic_employee_database`는 현재 보정 전후의 전체 백업을 임시 DB에 복원한 뒤 실행한다. 보조 표 초기화와 앱 검사 의존성은 위 #15 절차를 따른다.

복구: 적용 전 전체 덤프를 새 DB에 복원하고 적용 후 사용자 입력을 보존·대조한 뒤 연결을 전환한다. 현재 DB 전체를 즉시 덮어쓰지 않는다. 새 로컬 보완 백업에는 #26의 시간·목차(025·026)도 포함된다. 강좌 PR #32는 main에 병합됐으며, 직원 #27은 그 위에서 별도로 검토한다. 기존 Drive 공유본이 자동 갱신되지는 않는다. 사람 리뷰·커밋·푸시·배포는 별도 상태로 확인한다.

10/29 main `0a6dd08` 기준 업무/프로젝트 연결 검증: 무료 단위 222개 통과·5개 제외, 격리 DB/실제 인증 API 39개 통과, 프런트 15파일·53개 검사와 타입·lint·빌드 통과(lint 기존 경고 37개). 로그인 캐시·동시 작업 공유·입력 변경 중 옛 결과 폐기·실패 보존은 고정 응답으로 검증했다. 별도로 사용자 승인 후 OpenAI `gpt-6-luna`를 정확히 4회 호출해 4명×3개, 목표 후보 12개를 생성하고 모두 직접 검토했다. 입력 2,309·출력 4,778토큰이며 추가 재시도는 0회다. 원본에는 후보·이유·입력 해시/상태를 함께 저장했으며 직원 105명 전체 행과 후보 표 외 기존 52개 표를 보존했다. 기존 `app_ext` 초기화 SQL을 적용해 25개 보조 표를 포함했고, 최종 전체 백업의 78표·22,442행 지문이 복원 후 모두 일치했다. 생성 복제본과 새 백업 복원본 각각 12회 로그인/세션/목표 진입에서 추가 모델/작업은 0건이었다. 내부 브라우저에서도 프로젝트만 입력한 계정의 실제 후보 3개 즉시 표시를 확인했다. Drive 기존 두 파일은 최종본으로 교체하고 재다운로드 해시를 검증했다. [실제 생성·백업 기록](data/exports/actual_goal_preload_20261029.manifest.json)을 따른다. 다른 PC 배포·사람 재리뷰는 남아 있으며 앱 변경은 PR #29 배포가 필요하다.

10/29 최신 main `7d7de93`(PR #37) 추가 통합 검증: DB 단위 222개·5개 제외, 격리 DB/인증 API 39개, 분류·회사 정보 연결 단위 24개, 프런트 15파일·53개 검사와 타입·lint·빌드 통과(lint 기존 경고 37개). README 충돌은 분류 안내와 목표 사전 준비 안내를 모두 보존했다. main의 분류·검색·의존성·Docker 변경은 그대로 유지했다. 초기 임시 경로 권한 오류는 작업 폴더 TEMP를 지정해 재실행하여 통과했다. 이번 통합의 유료 호출·원본 DB 수정·Drive 백업 변경은 0건이다. 실제 RoBERTa 가중치 추론과 컨테이너 배포는 재실행하지 않았다.

10/29 추가 반영 · 현재 정책: TEST_MANUAL 100명에 사용자 승인한 `gpt-6-luna` 100회로 후보 300개를 저장했다. 팀원 5명과 기존 후보 12개를 보존해 전체 후보는 312개다. 입력 110,507·출력 91,847토큰이며 자동 재시도는 0회다. 300개 형식·근거 항목을 검사하고 6개 직무의 대표 12명·36개 후보를 직접 대조했다. 비슷한 접근 로그 업무의 직원 사이에 같은 문구 1종이 있으나 개인별 후보 3개는 서로 다르다. 로그인/세션의 생성·변경 검사는 제거하고 홈페이지 저장 성공 뒤에만 갱신한다. 부서/상위 부서·보유 자격명 변경의 누락도 보완했다. 무료 단위 222개·5개 제외, 격리 DB/API 42개, 프런트 53개와 타입·lint·빌드가 통과했다. 생성 복제본과 백업 복원본 각각 100명 로그인·세션·목표 진입에서 추가 생성 요청/AI 호출 0회를 확인했고 78표·23,342행 복원 지문도 일치했다. 실제 화면의 저장 후보·변경 시점 안내도 확인했다. 최종 Drive 두 파일을 교체하고 재다운로드 해시를 검증했다. [100명 생성·보존·백업 기록](data/exports/employee100_goal_preload_20261029.manifest.json)을 따른다. 코드 게시·사람 리뷰·다른 PC 배포는 각각 확인한다.

## 자료 벡터 갱신 계획과 선택 실행

이슈 #14 후속 기능이다. `plan`은 실제 DB에 읽기 전용으로 연결해 갱신할 유형·ID·누락/오래됨 여부·UTF-8 입력 바이트·32건 단위 배치 수를 출력한다. 원문, API 키와 벡터 값은 출력하지 않는다. 바이트 수는 토큰 수나 비용 견적이 아니다.

```powershell
# database/에서 실행. 실제 DB 필요. 임베딩 API 호출·DB 쓰기 없음.
python -m src.database.vectors.resource_vectors plan --resource-type books --max-records 25
# 필요하면 --resource-id를 반복해 ISBN별로 선택한다.
python -m src.database.vectors.resource_vectors plan --resource-type books --resource-id ISBN
```

원본은 전달 백업 이후 바뀔 수 있으므로 25건을 고정된 운영 수치로 보지 않는다. 최대 건수를 넘으면 일부만 처리하지 않고 실패한다. ID 선택에는 하나의 유형을 지정해야 하며 잘못된 ID·0 이하 최대 건수·8,000 UTF-8 바이트 초과 입력도 쓰기·유료 호출 전에 거절한다.

아래 `embed`는 **유료 API와 DB 쓰기**를 수행한다. 담당자·예산·실행 승인을 확인하고 현재 DB 백업을 보존한 후 실행한다. 이번 후속 준비에서는 실행하지 않았다.

```powershell
python -m src.database.vectors.resource_vectors embed --resource-type books --max-records 25
python -m src.database.vectors.resource_vectors plan --resource-type books --max-records 25
python -m src.database.vectors.resource_vectors status
```

실제 입력을 다시 임베딩한 결과와 해시를 함께 저장한다. 최신 자료는 다시 처리하지 않고 입력 해시만 바꿔 최신으로 표시하지 않는다. 기존 `embed`의 전체 유형 실행도 유지한다. API 실패·입력 변경은 DB 트랜잭션을 롤백하지만 이미 호출한 외부 API 비용은 복구되지 않는다. 적용 후 갱신 계획의 `pending_count=0`과 검색 경로를 실제 DB에서 확인해야 한다. 되돌릴 때는 실행 전 백업을 별도 DB에 복원해 대상 벡터를 복구하고 원본/입력 해시·모델 버전을 다시 대조한다. 해시만 과거 값으로 바꾸지 않는다.

10/28 최신 `main`의 `438b011`로 맞춘 뒤 `python scripts/check_workspace.py`에서 무료 단위 192개 통과·5개 제외를 확인했다. `tests.test_resource_refresh`의 선택·최대 건수·누락·UTF-8 한도·입력 변경·API 실패 검사 10개가 포함된다. 별도 복제 PostgreSQL에서 `tests.test_resource_refresh_database` 5개로 선택 갱신·무변경 재시도·갱신 후 pgvector 검색·API 실패·FK 실패·입력 변경 시 실제 롤백을 확인했다. 임베딩 응답만 고정 벡터로 대체했고 유료 호출은 0회다.

최신 실제 DB의 읽기 전용 `plan`·`status` 결과는 추천 대상 2,425개(스킬 36·강좌 2,045·자격 23·직무 6·전공 7·도서 308)가 모두 최신이며 갱신 대상은 0개다. 저장된 2,469개 중 44개는 현재 추천 적격 범위 밖이라 검색 대상에서 제외되며 삭제하거나 다시 임베딩하지 않았다. 10/21의 도서 25건은 과거 상태이므로 이번 유료 처리 대상으로 사용하지 않는다. 전체 DB 원본·벡터는 변경하지 않았다. 실제 추천/챗봇 검색 품질은 별도 평가 대상이다.

10/29 리뷰 보정 검증: 무료 단위 215개 통과·5개 제외, 실제 격리 DB/인증 HTTP 13개 통과, 화면 43개 테스트·타입 검사·빌드 통과(lint 기존 경고 37개). 목록→단건 상세→목차 펼치기를 브라우저에서 확인했다. 100건 목록은 약 1.26MB에서 0.20MB로 줄었다. 원본 DB 변경·유료 모델 호출은 없으며 변경은 로컬에서 검증했다.

10/29 선택 수정 추가 검증: 무료 단위 216개 통과·5개 제외, 실제 격리 PostgreSQL/인증 HTTP 16개 통과, 프런트 13파일·47개 테스트와 타입·lint·빌드 통과(lint 기존 경고 37개). 최신 검토 DB의 비공개 복사본에서 관리자 시간 확인 후 동기화 보존과 표시 문구/숫자 정밀도를 검사했다. 내부 브라우저에서 도서 전체 소개 접근·관리자 설명 변경 후 상세 재진입 갱신·단계와 실행 기록의 ‘5시간 50분’ 표시를 확인했다. 원본 DB 쓰기·유료 호출은 0회이며 실제 모델 추론은 검사하지 않았다.
