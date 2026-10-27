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

`check_import.py`는 파일 해시·현재 스키마·ERD·외부 백업 manifest를 대조하며 DB/API를 호출하지 않는다. `check_workspace.py`도 기본은 무료 단위 검사다. 이번 Git 준비본에서 단위 166개 실행·통과, 5개 건너뜀(외부 규정 원문 4개·DB 클래스 1개), 별도 복제 DB 통합 23개 실행·통과를 확인했다. 모의 HTTP 503 재시도 출력은 예상한 검사다. 실제 API·GPU 비용은 이번 Git 준비에서 사용하지 않았다.

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

직원 입력은 비공개 JSON으로 전달한다. 문서·강좌 적재와 보정의 입력·검토 증빙도 외부 자료다. `--apply`, 벡터 `embed`, 문서 질문 검색은 실제 DB 변경 또는 유료 API 호출을 수행할 수 있으므로 합의한 범위를 확인하고 실행한다. `load_data.py`의 일반 적재는 초기화 경로를 포함하므로 최신 백업 확인 목적으로 실행하지 않는다.

## ERD·산출물·호환성

```powershell
python -m src.database.erd
```

기본 템플릿은 `database/docs/erd_template.html`, 출력은 `docs/07_데이터베이스_저장소_설계/ERD_최종.html`이다. 과거 `--template`의 완성 HTML 방식과 `render_html()`도 유지한다. [구조 목록](../docs/07_데이터베이스_저장소_설계/SCHEMA.md)·[스키마 SQL](../docs/07_데이터베이스_저장소_설계/schema_final.sql)과 함께 본다. 화면 제어는 Chrome 현재 URL 확인 실패로 중단돼 새 기타 영역의 화면 검증은 미완료다. 표 포함·중복·FK·저장 위치 적용 조건은 정적으로 확인했다.

[DB 설계 대응표](../docs/07_데이터베이스_저장소_설계/README.md), [전처리 대응표](../docs/08_데이터_전처리_결과서/README.md), [벡터 검색 대응표](../docs/09_벡터DB_구축_결과서/README.md)에 구현을 연결했다. Word/PDF 제출 원본은 이번 준비에서 수정하지 않았다. 과거 Drive 일치 기록은 10/21 시점의 기록이며 현재 Drive 재대조 완료로 해석하지 않는다.

[import-manifest.json](import-manifest.json)은 원래 출처·해시와 이번 로컬 최종본의 파일 해시를 구분한다. [snapshot-audit.json](snapshot-audit.json)은 과거 정적 검사와 최신 복원·보정 검증을 구분한다. `src/db/` 호환 경로와 비밀값 미출력·외부 직원 seed 사전 거절 동작을 유지한다.

남은 검토: 근거가 약한 MLOps 10건, 강사 경력으로 OS 보안에 연결된 KMOOC_7204의 CI/CD 재분류, 사번이 없는 기존 REAL_USER 5명의 실제 사번 확인, 실제 추천 화면·챗봇 연동·다른 PC 실행·사람 리뷰. #14의 선택 벡터 갱신 작업과 #15의 권한·활동·코멘트 계약은 별도 작업이며 이번 준비로 완료 처리하지 않는다.
