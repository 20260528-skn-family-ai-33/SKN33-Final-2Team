# 챗봇 질문 분류 모델 연결

## 파일별 역할

| 파일 | 역할 | 실행 시점 |
| --- | --- | --- |
| [`app/question_classifier.py`](app/question_classifier.py) | `.pt` 모델·토크나이저 로딩과 질문 4분류 | 실제 모드에서 챗봇 질문 처리 시 |
| [`app/knowledge.py`](app/knowledge.py) | 회사 정보 범주의 실제 DB 원문·벡터 검색 | 수자원공사 정보로 분류된 질문 처리 시 |
| [`app/agents/regulation.py`](app/agents/regulation.py) | 분류 결과에 맞춰 검색·안내·LLM 답변 처리 | 챗봇 질문 처리 시 |
| [`app/errors.py`](app/errors.py) | 모델 연결 실패 원인과 조치 안내 | 오류 발생 시 |
| [`tests/test_question_classifier.py`](tests/test_question_classifier.py) | 연결 경로·파일 누락·실패 처리 단위 테스트 | 아래 테스트 명령을 직접 실행할 때만 |
| [`tools/check_classifier.py`](tools/check_classifier.py) | 실제 모델 로딩과 대표 질문 4개 분류 확인 | 아래 확인 명령을 직접 실행할 때만 |
| [`../requirements.txt`](../requirements.txt) | CPU 추론 패키지 버전 | 의존성 설치·Docker 이미지 빌드 시 |
| [`models/classifier-manifest.json`](models/classifier-manifest.json) | 모델·토크나이저 해시와 학습 라벨·입력 길이 | 모델을 처음 로드할 때 |

검증용 Python 파일 2개는 보관하며, 챗봇 사용이나 서버 시작 때 자동으로 실행하지 않아요. 실제 요청에서 동작하는 것은 학습이 끝난 모델의 **추론**이에요. 재학습은 하지 않아요. 모델 로딩 때의 파일 해시·라벨 확인은 실행 코드에 남아 있는 연결 보호 절차예요.

## 챗봇 처리 흐름

실제 모델 모드는 `질문 → RoBERTa(CPU) → 유형별 처리 → 기존 LLM 답변`으로 동작해요. 가데이터 모드는 기존 고정 응답을 유지해요.

| 학습 라벨 | 처리 |
| --- | --- |
| 범위 밖 | 규정 검색과 LLM 호출 없이 기존 범위 밖 안내 |
| 사내 규정 | 직원 구분에 맞는 기존 규정 검색·근거/숫자 검사·LLM 답변 |
| 사내 생활안내 | 기존 가상 사내 홈페이지 메뉴 안내. 규정 임베딩 호출 안 함 |
| 수자원공사 정보 | DB `knowledge`의 실제 회사 자료를 검색해 답변·출처를 제공. 근거가 부족하면 확인 불가 안내 |

회사 정보는 `knowledge.documents.category=수자원공사 정보`인 실제 자료만 검색해요. 확인한 DB에는 문서 3종·137개 청크와 벡터가 있어요. 가상 생활안내 305개 청크는 회사 정보 검색에서 제외하며, 생활안내는 기존 메뉴 안내를 유지해요. 연결 확인과 전체 검색 품질 평가는 구분해요. 짧은 이어 묻기는 기존 판별 규칙에 해당할 때 직전 질문 최대 120자를 함께 분류하고, `meta.classification.usedHistory`로 알려 줘요. 후속 질문의 전반적인 품질은 별도 평가가 필요해요.

## 분류 불일치 시 사용자 재확인 계획 (Human-in-the-loop)

2026-10-29 사용자 요청으로 정한 **후속 구현 계획**이에요. 이번 변경은 문서만 남기며, 아래 동작은 아직 코드에 적용하지 않았어요. 현재 분류와 답변 유형이 충돌하면 `AI_BAD_OUTPUT`이 발생하는 처리가 남아 있어요. 관련 [PR #37 인라인 리뷰](https://github.com/20260528-skn-family-ai-33/SKN33-Final-2Team/pull/37#discussion_r4409062326)도 구현 완료로 처리하지 않아요.

RoBERTa가 질문을 `사내 규정`·`사내 생활안내`로 분류했지만 LLM은 범위 밖으로 해석하는 등 **질문 해석이 엇갈리는 경우**에는, 오류 화면 대신 LLM이 이해한 질문을 사용자에게 되물어 확인받을 예정이에요.

1. RoBERTa 분류와 LLM의 질문 해석이 맞지 않거나 뜻이 애매하면, 확인 전에는 해당 해석으로 사실 답변을 확정하지 않아요.
2. 기존 `answer.kind=clarify`·`question`·`options` 형식을 활용해 LLM이 이해한 내용을 질문으로 보여 줘요. 사용자가 해석을 확인하거나 자신의 의도를 수정할 수 있어야 해요.
3. 사용자의 선택·수정과 앞선 확인 질문을 반영해 다시 분류하고, 확인된 의도에 맞게 검색·답변해요.

예를 들어 “부산 날씨 알려줘”가 `사내 규정`으로 분류됐지만 LLM이 일반 날씨 질문으로 해석하면, “부산의 일반 날씨를 물으신 건가요, 업무 중 기상 대응 규정을 물으신 건가요?”라고 되물어요. 선택한 의도가 서비스 범위 밖이면 기존 범위 밖 안내로 연결할 예정이에요. 이 문장은 예정된 응답 예시이며 실제 실행 결과는 아니에요.

### 사용자에게 확인할 문제와 시스템이 처리할 문제

| 상황 | 처리 계획 |
| --- | --- |
| 분류와 LLM의 해석이 달라 질문 의도를 확정하기 어려움 | 사용자가 뜻을 확인할 수 있으므로 `clarify`로 되묻기 |
| LLM이 약속한 JSON 구조를 지키지 않아 서버가 응답을 읽을 수 없음 | 시스템 오류로 처리. 재시도 여부·횟수는 후속 구현에서 정하며 현재 자동 재시도가 있다고 가정하지 않음 |
| 없는 인용 ID·근거 없는 숫자 등 답변 검증 실패 | 기존 검증을 유지하며, 사용자의 확인만으로 유효한 근거로 인정하지 않음 |

되묻기로 전환할 대상은 **질문 해석의 불일치로 발생하는 `AI_BAD_OUTPUT`**이에요. 같은 코드로 표시되는 응답 구조·출처 검증 오류까지 모두 되묻기로 바꾸지는 않아요. `backend/app/agents/regulation.py`의 LLM 프롬프트·분류 불일치 처리와 후속 대화 처리를 함께 맞추는 것이 구현 범위예요. RoBERTa 재학습은 이 계획에 포함하지 않아요.

AI 사용: Codex가 사용자 요청을 문서화했어요. 이번 변경에서는 문서의 용어·예시·링크·현재 구현과 계획의 구분을 확인했으며, 코드 수정·테스트·모델/API 호출·배포는 하지 않았어요. 구현·실제 동작 검증·사람 리뷰는 남아 있어요.

## 회사 정보 근거 연결

`app/knowledge.py`는 질문을 기존 OpenAI `text-embedding-3-small`로 1회 임베딩하고, 같은 모델·1536차원·원문 해시가 일치하는 저장 벡터만 코사인 유사도 0.25 이상·상위 5개로 읽어요. 문서의 회사 정보 범주와 `is_virtual=false`를 강제하고, 원문·기존 벡터를 갱신하거나 재임베딩하지 않아요. 저장 자료는 있는데 검색 벡터·설정이 준비되지 않았으면 오류로 알려요.

검색한 청크별 앞 3,000자와 문서명·위치·자료 기준 시점·원문 제약을 GPT Luna(또는 선택한 답변 모델)에 전달해요. 모델은 해당 원문으로만 답하고 사용한 청크 ID를 반환해요. 서버는 인용 ID가 실제 검색 결과에 있는지와 숫자 근거를 확인하며, 가상 자료·잘못된 출처·근거 없는 숫자는 성공으로 처리하지 않아요. 검색 결과가 없거나 원문으로 답할 수 없으면 확인 불가 안내를 반환해요.

회사 답변은 기존 `answer.kind=general`, `source=work` 형식을 유지하고 요약 끝에 출처를 덧붙여요. `answer.knowledgeSources`에는 청크·문서 ID, 문서명, URL, 원문 위치, 자료 기준 시점, 제약, 가상 여부, 원문/원본 파일 해시와 전달 텍스트 잘림 여부를 제공해요. 규정 조항의 `basis`와 섞지 않아요. 전용 출처 카드 UI는 추가하지 않았어요.

## 모델 파일과 설정

모델은 항상 `backend/models/klue_roberta_full_model.pt`에 둬요. 코드의 `MODEL_DIR`은 `backend/models/`로 고정하며 환경변수로 경로를 받지 않아요. 아래 `models/` 경로는 이 문서가 있는 `backend/` 기준이에요.

`models/`에는 사용자가 제공한 `klue_roberta_full_model.pt`, 학습 때 사용한 `config.json`·`tokenizer.json`·`tokenizer_config.json`, 해시·라벨·입력 길이를 기록한 `classifier-manifest.json`을 둬요. 토크나이저 출처와 파일 해시는 manifest에 있어요. `models/.gitattributes`는 Git 줄바꿈 변환을 끄고 JSON 원본 바이트와 해시를 보존해요. 가중치는 Git에서 제외하며 아래 팀 공유 폴더에서 별도로 받아요. 다른 PC에서도 manifest와 같은 가중치를 사용해야 해요.

### 팀원 PC에 가중치 배치

공유 위치: [RoBERTa 가중치 공유 폴더](https://drive.google.com/drive/folders/1jOvkc5NADpHGZ8J-ax9ZzRFrHpFjk5Qs) (사용자 제공, 2026-10-29).

1. 팀 Google 계정으로 공유 폴더를 열고 `klue_roberta_full_model.pt`를 다운로드해요. 접근이 거부되면 폴더 소유자에게 팀 계정의 접근 권한을 요청해요.
2. 파일을 `backend/models/klue_roberta_full_model.pt`에 둬요. 토크나이저·설정·manifest는 Git으로 받은 파일을 유지해요.
3. 저장소 맨 위에서 아래 명령으로 크기와 SHA-256을 확인해요. 기대 크기는 **442,613,817바이트**, SHA-256은 **`d369b4aad6df873e42f988571dab43e9177ef34e5e0336dcc0fd49f69eb94cd6`**예요. 해시는 대소문자를 구분하지 않아요.

```powershell
(Get-Item .\backend\models\klue_roberta_full_model.pt).Length
(Get-FileHash .\backend\models\klue_roberta_full_model.pt -Algorithm SHA256).Hash
```

4. 크기·해시가 다르면 모델을 실행하지 말고 공유 파일의 버전을 확인해요. manifest를 임의로 바꿔 통과시키지 않아요. 일치하면 아래 실행 절차로 진행해요. 팀 DB 백업·로그인·답변용 모델 설정은 저장소 README의 준비 절차를 따라요.

이 링크는 사용자가 지정한 배포 위치예요. 에이전트의 웹 도구에서 폴더가 열리지 않아 클라우드 파일 자체의 다운로드·해시와 팀원 계정 접근 권한은 확인하지 못했어요. 기대 크기·해시는 기존에 연결한 로컬 모델 기준이며, 실제 다운로드 파일과 대조해야 해요. 이 문서 갱신으로 실제 모델 추론이나 4개 유형 챗봇 검증이 완료된 것은 아니에요.

모델은 첫 실제 질문에서 한 번 로드하고 CPU에서 재사용해요. 학습과 같은 128토큰·패딩·라벨 순서를 사용하며, PyTorch `2.11.0+cpu`·Transformers `5.20.2`는 저장소 최상단 `requirements.txt`에 고정했어요. `backend/requirements.txt`는 기존 설치 명령 호환용으로 최상단 파일만 참조하며, 별도 분류기 requirements 파일은 두지 않아요. 전체 객체 `.pt`를 읽기 때문에 검증한 파일 해시가 맞을 때만 역직렬화해요. 토크나이저는 로컬 파일만 읽고 실행 중 다운로드하지 않아요. 모델·토크나이저 누락/변조·실행 실패는 `AI_CLASSIFIER`로 알리고 LLM 분류나 가데이터로 자동 대체하지 않아요. 실제 모델의 `config.id2label`도 학습 라벨 순서와 대조해요.

Docker는 `backend/models`를 `/srv/growpath/models`에 읽기 전용으로 붙여요. 모델 파일은 이미지 빌드에 포함되지 않아요. 호스트의 모델 위치는 항상 `backend/models/`이고 컨테이너에서는 같은 파일을 `/srv/growpath/models/`에서 읽어요. 최상단 requirements를 사용하도록 Docker 빌드 컨텍스트도 저장소 맨 위로 두고, `backend/Dockerfile.dockerignore`로 필요한 코드·의존성 파일만 허용해요. Windows의 Ollama를 Docker 백엔드에서 쓸 때 `.env`의 `OLLAMA_BASE_URL=http://host.docker.internal:11434`, `OLLAMA_MODEL`에는 Ollama에 설치된 **답변 생성 모델 이름**을 적어요. `.pt` 경로를 넣는 칸이 아니에요.

## 실행

저장소 맨 위에서 실행해요. DB·화면이 이미 실행 중일 때 백엔드만 반영하는 명령이에요.

```powershell
docker compose build backend
docker compose up -d --no-deps backend
```

## 검증용 파일 실행 방법 (선택)

챗봇 사용을 위해 아래 명령을 매번 실행할 필요는 없어요. 저장소 맨 위에서 필요할 때 직접 실행해요.

DB·LLM 연결 없이 가짜 입력으로 연결 경로와 실패 처리를 검사:

```powershell
docker compose run --rm --no-deps -T -v ./backend/tests:/srv/growpath/tests:ro backend python -m unittest discover -s tests -v
```

실제 가중치 로딩과 대표 질문 4개 확인(재학습·독립 평가·API 호출 없음):

```powershell
docker compose run --rm --no-deps -T backend python -m tools.check_classifier
```

이미지 삭제나 DB 볼륨 삭제는 필요 없어요. API `POST /assistant/ask` 결과의 `meta.classification`에 분류 모델·라벨·확률·소요 시간·앞 질문 사용 여부가 있어요. 기존 `answer.kind`와 화면 계약은 유지해요. 규정 검색에는 기존과 같이 OpenAI 임베딩 키가 필요하며, 분류 모델 연결이 이를 대체하지 않아요.

에이전트가 구현·검증한 범위와 미검증 항목은 작업 결과에 기록해요. 사람 담당자·검토자·일정은 미정이고, 사람 리뷰·팀원 백엔드 통합·병합은 별도예요.

## 초기 연결 작업 확인 기록 (2026-10-29)

아래는 초기 구현 시점의 기록이에요. 통합본과 회사 정보 연결의 후속 실제 확인은 다음 절에 구분해요.

- AI 사용: Codex가 분류 로더·질문 처리 연결·Docker 설정·테스트·문서를 작성했어요. 사람이 직접 시험하거나 리뷰했다는 기록은 아니에요.
- `python -m py_compile`(변경 Python 파일)·`git diff --check`: 통과.
- `docker compose build backend`: CPU 추론 의존성을 포함한 빌드 성공. `docker compose up -d --no-deps backend`로 백엔드만 재생성했어요. DB·화면 컨테이너는 유지됐어요.
- 외부 네트워크를 차단한 임시 컨테이너에서 `python -m unittest discover -s tests -v`: 19개 수집·실행·통과. 모델 누락·해시/라벨/길이 오류·분류 경로·LLM 유형 충돌·근거 없음·후속 질문·가데이터 분리를 검사했어요.
- 임시 컨테이너와 실행 중인 백엔드에서 각각 `python -m tools.check_classifier`: 실제 `.pt` 로드 성공, 대표 질문 4개를 실행했어요. 입력 4개의 예상 라벨과 일치했으며 독립 평가 결과로 해석하지 않아요.
- 실행 중인 백엔드의 `python -m pip check`: `No broken requirements found.` 모델·토크나이저는 읽기 전용으로 연결됐어요.
- 에이전트가 추가 분류/품질 테스트와 로그인·챗봇 HTTP 테스트를 실행하지는 않았어요. 이후 사용자가 직접 보낸 교육비 지원 질문의 기존 처리 기록에서 `status=done`, `meta.mode=openai`, `meta.model=gpt-6-luna`, `meta.classification.model=klue_roberta_full_model.pt`, `label=사내 규정`을 확인했어요. 사용자 화면에도 규정 답변이 표시됐어요. 이 한 건의 연결 확인을 전체 유형의 품질 평가로 해석하지 않아요. 에이전트가 유료 모델·임베딩 요청을 추가로 보내지는 않았어요.
- 관련 개발 이슈: [#36](https://github.com/20260528-skn-family-ai-33/SKN33-Final-2Team/issues/36). 초기 연결 앱의 403 이후 PC의 Git 인증으로 등록했어요. 담당자·검토자·기한·Notion/WBS는 미정이에요. PR 준비 단계에서는 사용자 요청으로 테스트를 재실행하지 않아요. 사람 리뷰·병합은 별도이며, #33의 규정 모델 역할 분리와 같은 파일을 수정하므로 최신 main 설정을 보존해 통합해요.

최신 main 통합 시 규정 답변·지원 조건 확인의 `role=regulation`과 기존 팀 Ollama 기본 모델 설정을 보존했어요. 이 통합본의 테스트는 사용자 요청으로 재실행하지 않았어요.

2026-10-29 추가 요청: 모델 경로 환경변수를 제거하고 `backend/models/`로 고정했어요. 백엔드·RoBERTa 의존성을 최상단 `requirements.txt`에 통합하고 Docker 설치 경로와 검증 코드의 임시 폴더 주입 방식도 맞췄어요. 이 추가 변경의 설치·빌드·테스트는 사용자 요청에 따라 실행하지 않았어요.

## 통합본 실제 연결 확인 (2026-10-29)

검증은 `roberta-review-37`이라는 별도 Docker 프로젝트에서 수행했어요. 기존 `growpath` 컨테이너·DB·사용자 세션은 유지했고, 가중치는 로컬 원본의 읽기 전용 링크로 연결했어요. Drive 파일의 다운로드와 팀 계정 접근 권한은 검증하지 않았어요.

### 통합 코드 `9499487`

- 최상단 `requirements.txt`를 사용하는 `docker compose ... build backend backend-setup`이 성공했어요.
- 복원한 시험용 백업에 `courses.duration_seconds`가 없어 초기 `backend-setup`은 실패했어요. 저장소 DB 안내에 따라 복제 DB에 원본 그대로인 025·026 마이그레이션을 적용한 후 초기화가 성공했어요. 최초 DB CLI 연결은 내부 호스트의 기본 TLS 요구로 실패해, 이 로컬 검증 DB 연결에만 `DB_SSLMODE=disable`을 사용했어요. 기존 사용 DB에는 적용하지 않았어요.
- 검증 구성을 사용한 `docker compose ... run --rm --no-deps -T backend python -m tools.check_classifier`를 **1회** 실행했어요. 실제 `.pt`를 로드했고 대표 질문 4개가 예상 라벨과 일치했어요.
- 합성 직원 `TEST_MANUAL` 계정으로 로그인(200), OpenAI 모드·가데이터 끔을 설정한 후 실제 `POST /api/v1/assistant/ask`를 **4회** 실행하고 로그아웃(204)했어요. 모델·검색·답변 응답을 가짜로 대체하지 않았어요.

| 질문 | 실제 분류 | HTTP·답변 결과 |
| --- | --- | --- |
| 오늘 부산 날씨 알려줘 | 범위 밖 | 200, `kind=out`, 답변 생성 모델 호출 생략 |
| 연차휴가는 며칠 사용할 수 있나요? | 사내 규정 | 200, `kind=regulation`, `level=ok`, 규정 근거 1건 |
| 구내식당 식단은 어디서 확인하나요? | 사내 생활안내 | 200, `kind=general`, `source=intranet`, `cafeteria` 메뉴 |
| 한국수자원공사는 어떤 일을 하는 기관인가요? | 수자원공사 정보 | 200, `kind=general`, 당시 회사 자료 검색이 없어 확인 불가 응답 |

위 네 번째 결과는 회사 정보 검색·근거 연결의 성공이 아니에요. 분류·요청 완료만 확인된 것으로 구분하고 아래 변경으로 보완했어요. 규정 검색 대상 895개 청크의 저장 벡터는 모두 있어 대량 재임베딩은 실행하지 않았어요.

### 회사 정보 연결 코드 `fea231f`

- 회사 정보 검색·출처 검사를 추가한 코드로 Docker 이미지를 다시 빌드했어요. 규정·생활안내·범위 밖 질문이나 전체 단위 테스트는 이 단계에서 반복하지 않았어요.
- 회사 정보 문서 3종·벡터 137개가 저장돼 있음을 확인한 뒤 같은 회사 소개 질문을 실제 챗봇 API로 **1회** 실행했어요. 서버가 아직 기동 중이던 최초 로그인 시도는 연결 거부로 끝나 챗봇·외부 API를 호출하지 않았고, 서버 준비를 기다린 후 진행했어요.
- 결과: HTTP 200, RoBERTa `수자원공사 정보`(확률 0.994711), 실제 답변 모델 `gpt-6-luna`, `kind=general`, `source=work`, 실제 인용 출처 **2건**. 약 14.7초가 걸렸으며 성능 벤치마크는 아니에요.
- 답변은 수자원·광역상수도 시설 건설·관리, 생활용수 공급·수질 개선, 산업단지·특수지역 개발, 지방 상하수도 수탁운영과 신재생에너지 설비 업무를 설명했어요. 문서 기준 시점도 출처에 함께 반환했어요.
- 실제 출처: `company-homepage-002`(K-water 공식 홈페이지 발췌, 공식 홈페이지 본문 요약, 2026-10-21 열람), `company-sr2025-004`(2025 K-water 지속가능경영보고서, PDF 9쪽, 2025 보고서 소개 기준·현재 운영 상태 별도 확인 필요). 두 자료 모두 `isVirtual=false`였어요.
- `answer.knowledgeSources`에서 해당 청크·문서 ID·URL·원문 위치·기준 시점·제약·해시가 반환되는 것을 확인했어요. 기존 `answer.basis`에는 회사 자료를 규정 조항처럼 넣지 않았어요.

실제 GPT Luna·질문 임베딩 API를 사용했고 금액은 별도로 집계하지 않았어요. 추가 유료 호출이나 전체 평가·재학습은 실행하지 않았어요. 결과를 보존한 뒤 검증용 컨테이너·복제 DB 볼륨·임시 모델 링크를 제거했고, 원본 모델과 기존 `growpath` 서비스가 유지된 것을 확인했어요.

이 결과는 대표 질문의 실제 연결 확인이에요. 기존 19개 단위 통과 기록 및 리뷰어의 `406d45a` 검사와 구분하며, 새 회사 정보 검증 케이스를 포함한 단위 테스트는 재실행하지 않았어요. 다른 PC·전체 브라우저 흐름·다른 회사 질문·후속 질문·Ollama 실제 답변과 인용 내용의 전반적인 정확성은 별도 검토 대상이에요. 이후 추가 변경은 API 선택 필드의 타입·문서·검증 기록이며, 회사 답변을 확인한 백엔드 실행 코드는 `fea231f`와 같아요. 현재 사용 중인 `localhost:8816` 서비스에는 이 새 코드를 배포하지 않았어요.
