# 프로젝트 산출물

이 폴더에는 2026-11-15에 기존 Drive 파일에 반영한 산출물 11종을 담았다. 파일 경로와 Drive 원본 링크는 유지한다.

- **본문 갱신 6종:** 요구사항 정의서·WBS·기획서·수집 데이터 보고서·DB/저장소 설계서·전처리 결과서. 프로젝트 지식 r717(main `c0ffbc1` 및 PR #265 반영 내용)을 기준으로 대조했다. WBS 일정·담당자·수식은 보존했다.
- **문구 정리 5종:** 모델 보고서·학습결과서·벡터DB 결과서·아키텍처·화면설계서. 변경이력과 작업 메모 표현을 정리했으며 기능 설명·수치·실험 결과·캡처는 기존 문서 기준을 유지했다.
- **현재 코드 설명:** 루트 [README](../README.md)는 2026-11-15 main `20f8a14` 기준이다. 문구만 정리한 문서의 과거 구현·실험 기록을 현재 코드 설명으로 해석하지 않는다.
- 파일별 SHA-256·크기·Drive 원본 URL·수정일·수정 범위는 [산출물 manifest](artifacts.manifest.json)에서 확인한다. `basis_date`는 이번 파일 수정일이며, 본문 기준은 `content_basis`에 표시했다. 문구 정리본의 `code_commit`은 특정 현재 커밋 전체를 반영한 것으로 오해하지 않도록 비워 두었다.

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

현재 챗봇은 ML 질문 분류·신뢰도 확인과 재분류·유형별 검색·답변 생성·응답 검증의 **1~5단계**로 처리한다. 사내 규정은 3-1·4-1·5-1단계, 회사 정보·사내 생활은 3-2·4-2·5-2단계로 구분한다. 함수별 흐름은 [챗봇 처리 흐름](../backend/classification.md#챗봇-처리-흐름)을 따른다.

현재 코드의 검색은 BGE-M3 1,024차원 벡터를 사용하며 사내 도우미는 BM25·pgvector 결과를 RRF로 결합한다. 문서에 남은 DB 수량·차원·백업 정보는 각 문서가 표시한 스냅샷과 실험 시점의 기록이다. 서로 다른 시점의 수치를 합산하거나 현재 운영 DB 전체 수량으로 사용하지 않는다.

[team_db 안내](../team_db/README.md)에 따라 덤프와 **같이 받은 manifest**의 SHA·크기를 확인한다. 현재 복원 절차는 [개발 환경 실행 안내](development-setup.md), 이전 복원 기록은 [DB 복원 안내](../database/RESTORE.md)를 따른다. 덤프·규정 원문·개인정보·모델 가중치는 이 폴더에 포함하지 않는다.

07 폴더의 ERD·schema_final.sql·SCHEMA.md는 기존 구조 자료로 유지한다. 이번에 교체한 통합 설계서와 별개이며 현재 스키마·마이그레이션은 [database](../database/README.md)를 따른다. 07·08·09 README의 예전 수치·Drive 일치·검사 결과는 표시된 날짜의 이력이다.

기존 모델 학습·val 선택 성적·대표 호출·단위 검사·복원 기록과 독립 품질 평가, 전체 사용자/목표·실제 두 모델 E2E·수신 PC·부하·사람 검토·운영 배포는 구분한다. 이번 저장소 배치에서 새 데이터 적재·DB 복원·모델/API 호출·운영 검증은 수행하지 않았다.

## 보존한 과거 자료

[중간 발표 자료](06_중간_발표_자료/GrowPath_중간보고_20261016_v4.pdf)는 기존 10/16 원본으로 보존했다. 앱에 원본이 없는 다른 종류의 산출물은 임의 생성하지 않았다.
