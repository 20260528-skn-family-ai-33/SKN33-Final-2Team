# DB 구현과 산출물 기록

2026-10-21 사용자 전달 DB의 코드·문서·정적 검사 기록이다. Word 원본은 전달 당시의 기록으로 보존한다. Drive 팀 폴더의 현재 산출물 3종과 원본 파일을 내려받아 SHA-256·ZIP 내부 파일·본문을 비교했고 모두 일치했다. 문서의 과거 수치·화면과 아래의 현재 백업 정보를 구분한다.

- [DB 설계 전달 원본](데이터베이스_저장소_설계_통합본.docx)
- [현재 ERD](ERD_최종.html) · [테이블·컬럼·외래키 목록](SCHEMA.md)
- [실행 코드](../../database/README.md) · [복원 절차](../../database/RESTORE.md)
- [원본·이관 파일 해시](../../database/import-manifest.json) · [전달 백업 manifest](../../database/data/exports/growpath_full_20261021.manifest.json)

## Drive 최신 파일과 관리 시트의 차이

확인 시점: 2026-10-21 16:54 KST. 아래 링크는 실제로 읽은 파일이며, Drive 문서나 관리 시트는 수정하지 않았다. 정확한 파일 SHA-256·Drive 수정 시각·관리 시트 연결 대상은 import manifest의 `drive_verification`에 기록한다.

| 산출물 | 팀 폴더의 현재 Drive 파일과 반영 예정 Word | 관리 시트의 현재 연결 |
|---|---|---|
| DB 설계 | [설계 통합본](https://docs.google.com/document/d/1QoI-BKqickgVZQ6yQZvW-eR7hXQhzlht/edit)과 바이트 동일 | `2팀!D14`는 [이전 설계 문서](https://docs.google.com/document/d/1s23TtDs8DXgfUbz_cB-OT_E7kyciOwSS/edit) 연결 |
| 전처리 | [현재 전처리 결과서](https://docs.google.com/document/d/1UJdY5QjMChedGc0dkF07hKrOlhOXEzdU/edit)와 바이트 동일 | `2팀!D15`는 [이전 전처리 문서](https://docs.google.com/document/d/176yxbR3-N4Zit7QwaV-C2DrcL-eJi21p/edit) 연결 |
| 벡터DB | [현재 벡터DB 결과서](https://docs.google.com/document/d/1ODZL0rrutkYhLRLpD-pLUEM5-UJNuxnv/edit)와 바이트 동일 | `2팀!D18`은 파일명만 있으며 조회한 셀에 하이퍼링크 없음 |

DB 설계·전처리는 관리 시트의 연결 문서보다 현재 통합본의 내용이 앞선다. 연결 문서는 본문 제출일이 10/14이고 통합본은 10/21이며, V18의 ID·자료형·복합 참조·결측 처리와 규정/운영 DB/학습 데이터 구분이 보완됐다. 파일 수정 시각만으로 판단하지 않고 본문을 대조했다. 관리 시트의 DB 설계·전처리 상태는 `작성(수정)중`, 벡터DB는 `제출완료`이며 검토 완료를 대신 확인한 것은 아니다.

일치한 최신 Word에도 이전 DB 건수가 남아 있다. 따라서 문서끼리는 최신 파일과 동일하되, 실제 백업의 최신 적재량과 프롬프트 FK 구조는 아래 표·현재 ERD·SCHEMA가 앞선다.

## ERD 반영 기준

사용자가 지정한 전달 폴더의 `project` 밖 `ERD_최종반영.html`을 화면 원본으로 사용한다. 직각 화살표, 표 이동·배치 저장, 검색·관계 강조, 운영/관리/보관 보기를 유지하고 내장 `D` JSON만 현재 catalog와 백업에 맞췄다. 화면 원본 파일은 수정하지 않았다.

외부 ERD의 이전 값에서 프로젝트의 `draft_prompt_version_id`·`plan_prompt_version_id`, 로드맵의 `prompt_version_id`와 FK·제약조건을 반영하고 10개 테이블 건수를 갱신했다. 전체 15,605행이던 화면 데이터는 현재 백업의 29,903행과 일치한다. [ERD 생성기](../../database/src/database/erd.py)는 템플릿 전체를 유지하고 JSON만 교체하므로 재생성 시 이 레이아웃을 보존한다.

브라우저에서 운영 42·관리 2·보관 6개 표, 운영 구조의 77개 화살표와 새 FK를 확인했다. 전체 열 표시·검색·구조 전환·표 이동/배치 저장/초기화를 실행했고 콘솔 오류는 0건이었다. 화면의 연결선 수는 같은 표 사이의 FK를 묶어 그린 값이며 전체 DB의 85개 FK 제약 개수와 구분한다.

## 같은 기준으로 읽을 현재 구조

백업 기준: `growpath_full_20261021.dump`, SHA-256 `cbdb5933f8a6e66874d805cdcae5fe9a466ecd7d872592732a37e526f6cad954`. 코드 원본: `necknam/fine-tuning`의 커밋 `a61c879096a422e0bf4e7821389a8fa268c550fa` 및 사용자 전달 문서. 파일별 출처와 보존/보완 여부는 import manifest에 기록한다.

| 항목 | 백업에서 확인한 값 |
|---|---:|
| 운영 / 관리 / 보관 테이블 | 42 / 2 / 6 |
| 전체 테이블 / 행 | 50 / 29,903 |
| 외래키 / manifest 제약조건 | 85 / 202 |
| 스킬 / 강좌 / 도서 | 36 / 1,149 / 3,327 |
| 자격증 / 직무 / 전공 | 68 / 80 / 132 |
| 자료 벡터 / 규정 벡터 | 4,792 / 1,410 |
| 현재 검색 대상 규정 청크 | 1,406 |

자료 벡터 중 도서 25건은 상태 변경 후 입력 해시가 오래됐다. ‘모든 벡터가 최신’이라는 전달 문서의 과거 문장을 현재 상태로 인용하지 않는다. 이전 718강좌·345도서·1,377자료 벡터 수치는 이전 스냅샷이다.

## 문서와 구현의 대응

| 설계 내용 | 구현 위치 |
|---|---|
| 테이블·FK·이전 구조 전환 | [마이그레이션](../../database/src/database/migrations/), [final_schema.py](../../database/src/database/final_schema.py) |
| 현재 구조와 검사 | [catalog.current.json](../../database/src/database/catalog.current.json), `final_schema.verify()` |
| 프로젝트·진단·로드맵·코멘트 저장 | [app_store.py](../../database/src/database/app_store.py), [db_client.py](../../database/src/database/db_client.py) |
| 백업·재현 | [portable.py](../../database/src/database/portable.py), 외부 자료 manifest |

단일 원본 관계, 복합 FK, 최초 로드맵 보존과 트랜잭션은 현재 구현의 설명이다. 요구사항과의 차이는 아래와 같이 미완료로 남긴다.

- 감독 그룹 직속 직원 권한 대신 부서·하위 부서 범위를 사용한다.
- 내 정보 수정/평정 동의, 학습 조건 저장 계약이 부족하다.
- 개별 활동 대신 단계 단위의 완료를 저장한다.
- 코멘트의 확인·선택적 버전 반영 상태를 구분하지 않는다.
- 직원 14명 중 부서장 표시 0명, 직무 연결 0명이다.

이관은 위 기능을 새로 구현하거나 목업을 DB에 연결하는 작업을 포함하지 않는다.

## 검증 주체와 범위

[snapshot-audit.json](../../database/snapshot-audit.json)은 에이전트가 전달 덤프를 직접 읽어 검사한 결과다. SHA-256·50테이블/29,903행, 기본키 중복과 85개 FK 참조값, 벡터 차원/유한값/영벡터, 원본 입력 해시를 정적으로 확인했다. 끊긴 참조와 비정상 벡터 값은 없었다. ERD·현재 메타데이터·백업 건수는 일치한다.

실제 PostgreSQL 복원, 트리거/RLS, 역할별 API, 검색 정확도·응답 속도는 이번 정적 검사의 범위가 아니다. 전달자의 별도 복원 PASS 기록은 전달자 기록이며 이번 실행으로 소급하지 않는다. 코드 이관 후 설치·CLI·단위 검사 결과와 변경 이유는 PR 검토 기록에 남긴다. 사람 리뷰는 별도다.

이관 시 Python 3.12 별도 환경의 `pip check`, CLI 도움말 8개와 Python 문법 검사를 통과했다. 선택한 단위 검사 42건 중 38건이 통과하고 외부 규정 패키지 4건은 자료 부재로 건너뛰었다. 실제 DB 회귀 검사 모듈은 실행하지 않았다. 신규 검사는 외부 덤프/직원 seed 누락·백업 해시 불일치가 비밀번호 입력이나 DB 작업 전에 실패하는지, ERD 재생성이 외부 레이아웃을 보존하고 잘못된 템플릿·스크립트 종료 문자열을 안전하게 처리하는지 확인한다. 원본 문서 3종과 적용 마이그레이션 12개의 바이트를 보존하며 `python scripts/check_import.py`로 이관 해시와 ERD/현재 메타데이터/백업 건수의 일치를 재확인할 수 있다.
