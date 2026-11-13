# 프로젝트 산출물

이 폴더에는 2026-11-03 본문·코드 대조를 마친 산출물 11종이 있다. WBS는 11월 4일에 수정된 Drive 파일이며, 요구사항 정의서에는 같은 날 WBS와 README 기준으로 담당자를 반영했다.

- **문서 작성 기준:** 2026-11-03 main `80cc597e56e56ff85bbc2c01e8b0ee2e5d8dd9a9`(PR57·61 및 PR61 P1 반영).
- **현재 README/코드 기준:** 2026-11-04 main `f8c27996dcc91b7dce9ac913dd79edb78b48a986`. PR60의 22종 테마, PR66의 자료 추천·공유 자료 일정 보정, PR70의 로드맵 생성 안정화가 이후 병합됐다. 문서에 남은 예정 표기는 11/3 작성 시점의 상태다. 최종 테마 선정·운영 검증은 구분한다.
- **기존 캡처:** 화면설계서의 71개 원본 그림은 10/28 main438b011의 당시 화면이다. 11/3에 정정한 본문·112개 API 계약 및 현재 테마 적용 화면과 구분한다. 화면 ID 46개·과거 실험 기록은 보존했다.
- **열린 PR:** PR65의 챗봇 상태 라벨 구분은 반영 예정이다.
- 파일별 전체 SHA-256·크기·Drive 원본 URL·기준일·코드는 [산출물 manifest](artifacts.manifest.json)에서 확인한다. Drive 링크는 같은 파일 ID의 내용이 이후 바뀔 수 있으므로 재현 기준은 저장소 파일과 SHA다.

| 산출물 | 저장소 파일 | Drive 원본 |
|---|---|---|
| 요구사항 정의서 | [파일](<01_요구사항_정의서/요구사항_정의서_33기_2팀.xlsx>) | [Drive](https://drive.google.com/file/d/1Kzv_qa8D6_3ZSddbo_IIcPsPNieaCcGD/view) |
| WBS | [파일](<02_WBS/WBS_33기_2팀.xlsx>) | [Drive](https://drive.google.com/file/d/1pgNlESKQp01VMze8cWLmJ4SyfepHqsek/view) |
| 프로젝트 기획서 | [파일](<03_프로젝트_기획서/GrowPath_기획서_33기_2팀.docx>) | [Drive](https://drive.google.com/file/d/1pM5mKfXJ8lH4HLiS0aRLpp3iDeYy0MUc/view) |
| 수집 데이터 보고서 | [파일](<04_수집_데이터_보고서/수집_데이터_보고서_33기_2팀.docx>) | [Drive](https://drive.google.com/file/d/1EkrTycoXmN4XYjQtKiR0UpgXFagbJ6b8/view) |
| 화면설계서 | [파일](<05_화면_설계서/화면_설계서_33기_2팀.pdf>) | [Drive](https://drive.google.com/file/d/10KQ9YMOopJowKSaTKA6MrGVgUz4BL9mQ/view) |
| 데이터베이스/저장소 설계 문서 | [파일](<07_데이터베이스_저장소_설계/데이터베이스_저장소_설계_통합본.docx>) | [Drive](https://drive.google.com/file/d/1QoI-BKqickgVZQ6yQZvW-eR7hXQhzlht/view) |
| 데이터 전처리 결과서 | [파일](<08_데이터_전처리_결과서/데이터_전처리_결과서_통합본.docx>) | [Drive](https://drive.google.com/file/d/1UJdY5QjMChedGc0dkF07hKrOlhOXEzdU/view) |
| 벡터DB/GraphDB 구축 결과서 | [파일](<09_벡터DB_구축_결과서/벡터DB·GraphDB 구축 결과서_33기_2팀.docx>) | [Drive](https://drive.google.com/file/d/1ODZL0rrutkYhLRLpD-pLUEM5-UJNuxnv/view) |
| 학습한 ML/DL 모델 보고서 | [파일](<10_학습한_ML_DL_모델보고서/학습한_ML_DL_모델보고서_33기_2팀.docx>) | [Drive](https://drive.google.com/file/d/1F0rkh3MZ0DPOUCVO1-1DgbM_8QCkPo_b/view) |
| 머신러닝·딥러닝 학습결과서 | [파일](<11_머신러닝_딥러닝_학습결과서/머신러닝_딥러닝_학습결과서_33기_2팀.docx>) | [Drive](https://drive.google.com/file/d/1WfgNa3pYP1i2FbFV5fWSc2fvIrOGqbs3/view) |
| AI 시스템 아키텍처(멀티 에이전트 아키텍처) | [파일](<12_AI_시스템_아키텍처/GrowPath_AI_시스템_아키텍처.pdf>) | [Drive](https://drive.google.com/file/d/1vzqDlfZE_T4KzbM_ohYnwERUtn66CU_T/view) |

## 데이터·구조·검증의 기준

챗봇의 현재 작업 브랜치(#138) 단계 표기는 **1~5단계**이며, 사내 규정은 3-1·4-1·5-1단계, 사내 생활안내·수자원공사 정보는 3-2·4-2·5-2단계로 구분한다. 함수별 흐름은 [챗봇 처리 흐름](../backend/classification.md#챗봇-처리-흐름)을 따른다. [PR #238](https://github.com/20260528-skn-family-ai-33/SKN33-Final-2Team/pull/238)은 검토 중이며, 아래 산출물의 과거 작성 기준과 구분한다.

문서의 DB 수치는 10/30 공유 스냅샷 `2026-10-30-price83-vectors71`의 기록이다. 전체 78표·23,567행은 기준 53표·22,727행과 app_ext 25표·840행의 합계이며 실행 중인 현재 서버를 다시 센 수치가 아니다. 자료·스킬 벡터 2,469개 중 적격 2,426개, 규정 1,410개 중 검색 대상 1,406개, 회사·생활 4문서 442청크를 구분한다. 벡터 개수·최신성은 추천·답변 정확도를 뜻하지 않는다.

[team_db 안내](../team_db/README.md)에 따라 덤프와 **같이 받은 manifest**의 SHA·크기를 확인한다. [DB 복원 안내](../database/RESTORE.md)와 저장소의 `database/data/exports/growpath_latest.manifest.json`에는 10/29 checkpoint가 남아 있다. 10/30 덤프 `dd9371849e26a4d5d4c168534749be4d277f061048ddf21bd46a9ee47dbfd256`(38,401,849바이트)와 그 이전 해시를 혼용하지 않는다. 덤프·원문·개인정보·가중치는 이 폴더에 포함하지 않는다.

07 폴더의 ERD·schema_final.sql·SCHEMA.md는 기존 범위의 구조 자료로 유지한다. 문서 속 핵심 14표 그림, 기준 53표 구조와 app_ext를 포함한 전체 78표 백업을 같은 범위로 해석하지 않는다. 07·08·09 README의 예전 수치·Drive 일치·검사 결과는 표시된 날짜의 이력이다.

기존 모델 학습·val 선택 성적·대표 호출·단위 검사·복원 기록과 독립 품질 평가, 전체 사용자/목표·실제 두 모델 E2E·수신 PC·부하·사람 검토·운영 배포는 구분한다. 이번 저장소 배치에서 새 데이터 적재·DB 복원·모델/API 호출·운영 검증은 수행하지 않았다.

## 보존한 과거 자료

[중간 발표 자료](06_중간_발표_자료/GrowPath_중간보고_20261016_v4.pdf)는 기존 10/16 원본으로 보존했다. 앱에 원본이 없는 다른 종류의 산출물은 임의 생성하지 않았다.
