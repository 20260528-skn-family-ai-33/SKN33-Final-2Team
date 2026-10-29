# 외부 DB 자료와 복원 · 2026-10-29

최신 공유본은 `growpath_latest.dump`와 같은 위치의 `growpath_latest.manifest.json`이다. 덤프 SHA-256 `e27fb83895f4080cbf8838765de577c360007d6b95cc8c2cc0c92b9979dd3ea7`, 38,402,877바이트다. 강좌 시간·커리큘럼(025·026), 가상 직원 100명의 이름·표시 문구 정리와 기존 업무/경험, 팀원 5명 및 실제 목표 후보 315개(105명×3개)를 포함한다. 개인 입력을 제외했던 직원의 업무·경력·프로젝트는 추가하지 않고 기존 소속·직무·보유 자격으로 후보 3개를 생성했다. 데이터의 가상 출처 기록은 내부에 보존한다.

[공유 폴더](https://drive.google.com/drive/folders/1DyJ67R5bYMEwKF-PChdOcxGF8TCNtPsx)에서 두 파일을 받는다. 기존 링크와 공유 권한을 유지했으며 업로드 후 다시 내려받아 두 파일의 SHA-256을 대조했다. [외부 자료 manifest](assets.manifest.json)와 [현재 백업 manifest](data/exports/growpath_latest.manifest.json) 및 [최종 품질 점검](data/exports/final_quality_20261029.manifest.json)에 버전·검증을 연결했다. 원문·개인 입력·덤프·비밀키는 Git에 넣지 않는다.

## 새 DB 복원

Python 3.12, PostgreSQL 17, pgvector가 필요하다. 최종 백업·독립 복원은 PostgreSQL 17.10·pgvector 0.8.2 Linux 컨테이너에서 검사했다. 앞선 Windows 17.11 검사와 구분한다. 설치는 [README](README.md)를 따른다. 가상환경을 활성화한 뒤 `database/`에서 실행한다.

```powershell
python scripts/restore_db.py restore --archive "<외부 백업 폴더>/growpath_latest.dump" --initialize --write-config --port 55435 --pg-bin "C:/실제_PostgreSQL_설치/bin"
python scripts/db.py migrate
python scripts/db.py verify
python -m src.database.vectors.resource_vectors status
```

비밀번호는 출력되지 않는 터미널 입력을 사용한다. 기존 DB·데이터 디렉터리·`.env.local`은 덮어쓰지 않는다. 기존 서버라면 `--initialize`를 생략하고 비어 있는 새 DB 이름을 지정한다. 포트가 사용 중이면 점유자를 먼저 확인한다. 설치 바이너리와 서버 확장은 별도로 준비한다. 복원에는 OpenAI 키나 유료 API 호출이 필요 없다.

이번 전체 덤프는 기준 스키마 **53표·22,727행**과 기존 앱 보조 스키마 `app_ext` **25표·840행**, 합계 **78표·23,567행**이다. 기준 표 구조는 유지하고 정적 ERD의 건수는 현재 기준 53표·22,727행으로 맞췄다. `inventory`는 기존 복원 도구와 호환되는 기준 53표이며, 전체 78표 지문은 manifest의 `all_schema_table_fingerprints`에 따로 기록한다. 기본 복원 도구는 기준 inventory를 대조하고, 작성 PC의 이번 추가 검사는 전체 78표와 실제 로그인 API까지 검증했다.

목표 후보는 `public.employee_recommended_prompts`, 이유·근거는 `app_ext.goal_suggestion_meta`, 입력 해시·상태는 `app_ext.goal_suggestion_runs`에 있다. `public`만 복원하면 사전 로딩 상태가 누락되므로 **전체 덤프를 복원한다**. 이번 최종 백업 복원본에서는 105명의 원래 생성 입력·목표 조회·갱신 필요 판정을 검사해 기존 후보 재사용과 추가 생성 0회를 확인했다. 로그인·세션을 포함한 실제 API 흐름은 별도 35개 검사로 확인했다. 105명 전체 로그인 검사는 앞선 natural105 checkpoint의 기록이다. 로그인의 변경 검사는 제거했으며 홈페이지 저장 성공 뒤 관련 직원만 갱신한다. SQL 직접 수정 후에는 후보를 명시적으로 다시 만든다. 새 업무/프로젝트 저장 계약과 자동 갱신에는 PR #29의 백엔드·프런트 배포도 필요하다.

세 Track 활성 프롬프트는 Free `agent_certified v3`, Fast `agent_fasttrack v4`, Challenge `agent_practical v3`이며 PR #41 정책과 PR #29의 프로젝트 경험 안내를 포함한다. 최신 앱의 `app_ext.user_settings.reasoning` 열도 포함한다. 전체 백업 수신자는 Track 프롬프트 설치·목표 재생성·임베딩을 다시 실행할 필요가 없다.

앱 추가 준비가 필요하면 `backend/tools/setup_db.py --supplement-only --keep-team-passwords`를 사용해 기존 직원 암호를 보존한다. 준비 도구는 저장된 목표 생성 상태가 있으면 초기 가데이터 후보로 덮지 않는다. API 키·직원 사번/암호·관리자 계정 설정은 저장소 밖에서 관리한다. 수신 PC의 실제 실행·배포는 아직 검증하지 않았다.

013~020 원본 SQL이 없어 빈 DB를 SQL만으로 재구성하거나 구판 10/21 DB에 021·022만 적용하는 방식은 지원하지 않는다. 최신 백업의 001~026 이력을 검증하고 이미 적용한 SQL의 바이트·해시를 바꾸지 않는다. 024의 조회 정책은 본인 또는 같은 기관·같은 부서의 부서장에게만 허용하며 부서 상하 관계는 사용하지 않는다.


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

```powershell
python scripts/restore_db.py backup --output "<외부 백업 폴더>/growpath_새버전.dump"
```

백업 도구는 `app_ext`를 포함한 모든 스키마를 덤프하지만 기본 inventory는 기준 53표다. 공유 전 앱 보조 표의 후보/이유/입력 해시를 별도로 확인한다. 복구는 검증된 이전 전체 백업을 새 DB에 복원·검사한 뒤 연결을 전환한다. 이후 사용자 입력이 있으면 먼저 보존·대조한다. PostgreSQL 내부 파일이나 다른 PC의 `.venv`를 실행 환경으로 복사하지 않는다.

시간·커리큘럼만 포함한 앞선 checkpoint는 `growpath_curriculum_20261028.dump` SHA-256 `c401c1f60e0b7d2e513dce031225cc2dad0d879ec22674900608b55c31d2c48c`이며 로컬 원본을 보존한다. 최신 Drive 파일에는 그 내용과 이후 인사/목표 작업이 함께 들어 있다. 중간 인사·실제 생성 전 백업의 해시는 각각의 외부 자료 manifest를 따른다.
