# 전처리 결과서와 구현 연결

[전처리 결과서 전달 원본](데이터_전처리_결과서_통합본.docx)은 원문 바이트를 보존한다. 과거 수치와 학습 데이터 설명이 포함된 전달본이며 이번 작업에서 데이터셋을 재구축하거나 파인튜닝하지 않았다. 최신 DB 수치는 [DB 기준표](../07_데이터베이스_저장소_설계/README.md)를 따른다.

2026-10-21에 [Drive 팀 폴더의 현재 파일](https://docs.google.com/document/d/1UJdY5QjMChedGc0dkF07hKrOlhOXEzdU/edit)을 내려받아 SHA-256·ZIP 내부 파일·본문이 모두 같음을 확인했다. 로컬의 `통합본`과 Drive의 `33기__2팀`은 파일명만 다르다. 관리 시트가 연결한 10/14 문서는 별도 이전 내용이며, 현재 파일에는 V18 수치·ID·근거·미확인 사항과 운영 DB/학습 데이터의 구분이 보완됐다. [세 문서 비교 결과](../07_데이터베이스_저장소_설계/README.md#drive-최신-파일과-관리-시트의-차이)를 함께 읽는다.

| 입력 → 처리 → 출력 | 주요 코드 |
|---|---|
| 공식 자료 API → 상세 확보·정제·원본 키 보존 → 자료 마스터/수집 이력 | [real_data_ingestor.py](../../database/src/database/ingestion/real_data_ingestor.py), [catalog_details.py](../../database/src/database/ingestion/catalog_details.py) |
| 자료 본문 → 품질·이용 가능성 확인 → 추천 대상 판별 | [catalog_quality.py](../../database/src/shared/catalog_quality.py), [catalog_eligibility.py](../../database/src/shared/catalog_eligibility.py) |
| 본문·기존 스킬 → 패턴 매칭 → 자료–스킬 관계 | [skill_matching.py](../../database/src/shared/skill_matching.py), [rules.yaml](../../database/config/rules.yaml) |
| 버전 지정 규정 패키지 → 정제/참조 검증 → 규정·청크·출처 적재 | [deployment.py](../../database/src/database/deployment.py) |
| 원본 필드·스킬 관계 → 입력 해시 → 별도 벡터 테이블 | [resource_vectors.py](../../database/src/database/vectors/resource_vectors.py) |

백업의 적재 건수와 추천 가능한 자료 수, 학습 데이터 샘플 수는 서로 다른 집계다. 현재 백업은 강좌 1,149·도서 3,327·자격증 68·직무 80·전공 132·스킬 36건이다. 의미 적합성의 전수 검수나 추천 정확도를 입증하는 값은 아니다.

문서의 1,500건 학습·분할·출처 기록은 전달 문서의 범위다. 학습 데이터와 `qwen_factory/`는 이번 DB 코드 이관에 포함하지 않는다. 규정 원문·원천 데이터도 [외부 자료 manifest](../../database/assets.manifest.json)에 파일 버전·해시만 연결했다. 실제 접근 위치는 미지정이다.

형식·해시·경로·벡터 값 등 단위 검사는 `database/tests/test_db_deployment.py`, `test_catalog_expansion.py`, `test_regulation_vectors.py`에 있다. 수집 코드의 테스트는 모의 응답을 사용하며 실제 외부 API의 이용 가능성·내용 정확도 검사와 구분한다.
