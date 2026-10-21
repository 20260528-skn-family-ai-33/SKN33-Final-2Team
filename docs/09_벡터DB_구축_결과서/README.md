# 벡터DB 결과서와 구현 연결

[벡터DB 구축 결과서 전달 원본](벡터DB·GraphDB 구축 결과서_33기_2팀.docx)을 보존한다. 제목의 GraphDB는 양식 명칭이며 이 구현에서 그래프DB 노드·엣지를 생성한 것은 아니다. PostgreSQL + pgvector의 벡터 검색을 사용한다.

2026-10-21에 [Drive 팀 폴더의 현재 파일](https://docs.google.com/document/d/1ODZL0rrutkYhLRLpD-pLUEM5-UJNuxnv/edit)을 내려받아 SHA-256·ZIP 내부 파일·본문이 모두 같음을 확인했다. 관리 시트의 `2팀!D18`에는 파일명만 있고 조회한 셀에 하이퍼링크는 없었다. Word가 현재 Drive 파일과 같다는 사실과, 아래의 실제 백업 수치가 Word보다 최신이라는 사실을 구분한다.

| 항목 | 현재 전달 구현 |
|---|---|
| 임베딩 | `text-embedding-3-small`, 1,536차원 |
| 자료 벡터 | `public.learning_resource_embeddings`, 4,792개 |
| 규정 벡터 | `regulations.rag_chunk_embeddings`, 1,410개 |
| 현재 규정 검색 대상 | active 1,406청크, 원본 해시 일치 |
| 검색 | DB 안에서 `<=>` 코사인 거리 계산, 현재 exact search |
| 자료 최신성 | 스킬·본문·출처 상태 등으로 입력 해시 비교. 도서 25건 갱신 필요 |

| 처리 | 구현 |
|---|---|
| 자료 입력·해시·저장·검색 | [resource_vectors.py](../../database/src/database/vectors/resource_vectors.py)의 `sources`, `embed`, `similarities` |
| 규정 청크·시행일·검토 상태·출처 필터 | [regulation_vectors.py](../../database/src/database/vectors/regulation_vectors.py)의 `SOURCE_SQL`, `SEARCH_SQL`, `search` |
| 벡터 원본 FK·유형/차원 제약 | [마이그레이션](../../database/src/database/migrations/), [현재 구조](../07_데이터베이스_저장소_설계/SCHEMA.md) |
| 잘못된 차원·NaN·영벡터·긴 입력 검사 | [test_regulation_vectors.py](../../database/tests/test_regulation_vectors.py) |

전달 원본 문서의 1,377자료 벡터는 이전 시점의 수치다. 현재 4,792개 중 도서 25건은 상태가 NULL에서 ready로 바뀐 뒤 입력 해시가 갱신되지 않았다. 이 자료가 후보에 포함되면 `similarities()`의 최신성 검사에서 거절될 수 있다. 이번 이관에서 유료 재임베딩은 실행하지 않았다.

보존한 규정 벡터 중 4개는 현재 검색 대상 밖이다. 저장 개수와 실제 검색 대상을 구분하며, 자료 벡터와 규정 벡터를 무조건 혼합하지 않는다. 기관·직원 구분을 검색에 전달하는 서비스 연결은 별도 확인이 필요하다.

[정적 검사](../../database/snapshot-audit.json)는 해시·값·차원·참조 무결성 근거다. 검색 정확도·응답 시간·LLM 답변 품질은 측정하지 않았다. HNSW/IVFFlat 인덱스 성능이나 GraphDB 구축을 완료했다고 기록하지 않는다.
