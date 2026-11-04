# 외부 DB 자료와 복원 · 2026-11-04

현재 공유본은 [growpath_latest.dump](https://drive.google.com/file/d/1hqEq-TSZhkPny9uOll9H_SdM8R5FU9GT/view?usp=drivesdk)와 [growpath_latest.manifest.json](https://drive.google.com/file/d/1ryFpLp9AgVN3b4TY5CpLxmsmhp7JDnXG/view?usp=drivesdk)이다. 기존 Drive 파일 ID와 공유 위치를 유지했다. 덤프 SHA-256 `e166efe51e34883d82997f24f5c182e9bffb0229253ee2633df487eb9321f968`, 42,892,937바이트이며 업로드 후 두 파일을 다시 내려받아 원본 해시와 일치함을 확인했다.

도서는 **334→849권(+515권)**, 도서 스킬 연결은 636건 추가했다. 36개 스킬 모두 연결 도서가 3권 이상이다. 신규 도서의 출처·벡터·앱 메타데이터도 포함한다. 최신 Drive 백업(교체 전 SHA-256 `218533512a098a21b95f79ce0d63a00cfacb727504976833d3266e38f0ca054b`)을 기준으로 추가했으며 기존 직원 105명·프롬프트·로드맵·기타 모든 행을 보존했다. 오래된 도서 검증 DB 전체로 공유본을 덮지 않았다.

전체 **78표·29,246행**을 새 격리 DB에 복원해 전 행 지문, 함수, 열·제약조건 및 시퀀스를 대조했다. 기본 복원 도구의 `inventory`는 기준 53표·25,102행이고 `app_ext`를 포함한 전체 지문은 `all_schema_table_fingerprints`에 있다. 스키마 변경은 없으며 ERD는 행 수만 갱신했다. 로컬 앱 DB는 변경하지 않았다.

## 새 DB 복원

PostgreSQL 17·pgvector, Python 3.12와 [README](README.md)의 의존성이 필요하다. 검증 서버는 PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2)이다. `database/`에서 다음을 실행한다.

```powershell
python scripts/restore_db.py restore --archive "<외부 백업 폴더>/growpath_latest.dump" --initialize --write-config --port 55435 --pg-bin "C:/실제_PostgreSQL_설치/bin"
python scripts/db.py migrate
python scripts/db.py verify
python -m src.database.vectors.resource_vectors status
```

기존 서버라면 `--initialize`를 생략하고 비어 있는 새 DB 이름을 지정한다. 기존 DB·환경설정을 바로 덮지 않는다. **public만 선택하지 말고 app_ext를 포함한 전체 덤프를 복원**한다. DB 준비가 필요할 때는 `backend/tools/setup_db.py --supplement-only --keep-team-passwords`로 기존 암호를 보존한다. 복원에는 유료 API 호출이 필요 없다. 수신 PC 복원·앱 배포는 아직 검증하지 않았다.

LLM 입력에 스킬별 적합 도서 최소 3권을 우선 확보하는 코드는 #76의 별도 변경이다. 실제로 3권 미만이면 가능한 수와 부족 정보를 전달하며, 최종 추천 수를 강제로 늘리지 않는다. DB 파일만 바꿔서는 이 후보 구성 코드가 배포되지 않는다. 도서 추가 수집 경로는 #83이며 기존 ISBN·강좌·직원·로드맵을 수정하지 않는다.

013~020 원본 SQL이 없어 구판 DB에 일부 SQL만 적용하는 대신 전체 백업을 새 DB로 복원한다. 비밀키·원문·덤프·개인정보는 Git에 올리지 않고 [외부 자료 manifest](assets.manifest.json)에 해시와 공유 링크만 연결한다. 이전 Drive 파일 쌍은 작성 PC에 보관했으며, 되돌릴 때는 이전 검증 백업을 새 DB에 복원하고 그 이후 사용자 입력을 대조한 뒤 연결을 전환한다.

## 이전 검증 기록 · 2026-10-29~30

아래 내용은 당시 백업·검사 기록이다. 현재 파일 해시·행 수·프롬프트 상태·배포 순서는 위 최신 안내를 기준으로 한다.

## 10/29 최종 보정과 적용 순서

이번 백업은 55강좌의 목차 표시 1,091개를 보정했다. 1,075개는 같은 원문 행의 학습 제목으로 표시하고 16개는 제목 미제공으로 구분했다. 원래 제목·설명·주차·출처 해시는 보존한다. `KMOOC_7204`는 시스템·OS 보안(33)에서 CI/CD 배포 자동화(21)로 연결을 바꾸고 실제 벡터 1건을 재생성했다. 직원 105명과 기존 추천 315개, 원문·가격·기간·시간은 변경하지 않았다.

팀원은 **새 전체 백업을 복원한 뒤 PR #41이 반영된 최신 main을 통합한 PR #29의 최종 코드를 반영하고 앱을 다시 빌드**한다. 복원 대상 DB를 가리키도록 기존 환경설정을 확인한다. 기존 DB를 유지할 경우 먼저 별도 백업과 복제본을 만들고 아래 데이터 보정의 적용 전후를 비교해야 한다.

- 목차 보정은 `python scripts/backfill_course_curriculum.py`로 계획을 확인하고 `--apply`로 적용한다. 이 백업에서는 변경 0건이며 유료 호출은 없다. SQL 001~026을 편집하지 않는다.
- 스킬 보정의 원문 SHA-256·이전/이후 스킬·근거는 [최종 품질 기록](data/exports/final_quality_20261029.manifest.json)의 `skill_correction_plan`에 있다. 기존 `src.database.course_skill_corrections.apply_corrections`에 이 계획을 전달하면 링크와 실제 벡터를 한 트랜잭션으로 갱신하며, 이미 반영된 상태에서는 0건이다. 구판 DB의 추가 임베딩은 별도 비용 승인이 필요하다. 기존 배포 전용 CLI는 원래 작업 PC의 포트·복제 검증 파일을 요구하므로 수신 PC에서 그대로 실행하지 않는다.
- 추천 해시 불일치 1명은 실제 입력 변경이 아닌 Windows/Linux 정렬 차이였다. 코드가 사내 스킬·등록 자격 목록을 일정하게 정렬하도록 수정했고, 105명의 원래 생성 입력과 해시가 모두 일치했다. 직접 입력한 목록 순서와 추천 원문·해시는 바꾸지 않았다.

남은 데이터 한계: 가격 미확인 83강좌, 계획 시간 추정 330강좌, 목차 일부 제목 미제공 9강좌·소개만 제공 6강좌. 전체 315개 형식·근거 항목과 대표 23명·69개 의미를 AI가 점검했다. 가상 직원의 공통 문장 틀과 사람 검토 필요는 남는다. 실제 모델의 전체 추천 품질 평가나 모든 강좌 사이트 재접속 검사는 하지 않았다. Free Track의 자격증 데모 실패·확정 전 가격 재검사는 별도 코드 후속 작업이다.

백업 생성 뒤 격리 복원본에서 실제 `gpt-6-luna` 입력→진단→3 Track→확정·재조회까지 확인했다. 공유 DB는 변경하지 않았다. 규정의 잘못된 미등록 표시, 진단 미리보기 예산 필터, 사용 프롬프트 버전 미저장과 추천 다양성은 별도 코드 후속으로 남는다. 이 검사는 직원 1명·전체 흐름 1회이며 모든 사용자 조합이나 RunPod 평가를 뜻하지 않는다. [최종 품질 기록](data/exports/final_quality_20261029.manifest.json)의 `post_backup_ui_verification`에 범위·호출량·미검증 항목을 남겼다. 공유 백업 manifest의 `application_verification`은 백업 생성 시점의 검사 기록으로 보존한다.

바로 이전 전체 DB·manifest는 [최종 보정 전 백업](https://drive.google.com/drive/folders/1wW9sey0PHMX2iSfNkNqu4RrTr0g0HjiZ)에 보존했다. 되돌릴 때는 해당 쌍을 새 DB에 복원하고 이후 사용자 입력을 대조한 뒤 연결을 전환한다. 현재 앱 코드를 같이 되돌릴지 호환성을 확인한다.

## 백업·되돌리기

10/30 #35 보충 적재·목차 캐시 수정은 PR #29 코드 배포에 포함된다. 공유 백업의 78표·23,567행을 복원해 확인한 결과 시간·목차 재보정 대상은 0건으로, Drive DB/manifest를 다시 교체하거나 별도 SQL 마이그레이션을 적용할 필요가 없다. 이후 신규 강좌는 등록 시 시간·목차를 함께 저장한다. 기존 샘플 목차의 전체 원문 HTML을 확보한 경우에는 `backfill_course_curriculum.py`의 읽기 전용 계획과 해시를 확인한 뒤 적용한다. 파일을 확보하지 못한 목차는 미확보 상태를 유지한다. 수집 시각의 UTC/한국 시간 표기만 다른 경우에는 기존 근거를 보존한다. 이 코드 수정은 별도 앱 후속 문제나 사람·RunPod 검증의 완료를 뜻하지 않는다.

```powershell
python scripts/restore_db.py backup --output "<외부 백업 폴더>/growpath_새버전.dump"
```

백업 도구는 `app_ext`를 포함한 모든 스키마를 덤프하지만 기본 inventory는 기준 53표다. 공유 전 앱 보조 표의 후보/이유/입력 해시를 별도로 확인한다. 복구는 검증된 이전 전체 백업을 새 DB에 복원·검사한 뒤 연결을 전환한다. 이후 사용자 입력이 있으면 먼저 보존·대조한다. PostgreSQL 내부 파일이나 다른 PC의 `.venv`를 실행 환경으로 복사하지 않는다.

시간·커리큘럼만 포함한 앞선 checkpoint는 `growpath_curriculum_20261028.dump` SHA-256 `c401c1f60e0b7d2e513dce031225cc2dad0d879ec22674900608b55c31d2c48c`이며 로컬 원본을 보존한다. 최신 Drive 파일에는 그 내용과 이후 인사/목표 작업이 함께 들어 있다. 중간 인사·실제 생성 전 백업의 해시는 각각의 외부 자료 manifest를 따른다.
