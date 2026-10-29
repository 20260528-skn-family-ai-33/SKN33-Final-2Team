# 챗봇 질문 분류 모델 연결

## 파일별 역할

| 파일 | 역할 | 실행 시점 |
| --- | --- | --- |
| [`app/question_classifier.py`](app/question_classifier.py) | `.pt` 모델·토크나이저 로딩과 질문 4분류 | 실제 모드에서 챗봇 질문 처리 시 |
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
| 수자원공사 정보 | 기존 일반 답변 형식. 입력 자료에 없는 기관 사실은 확인 불가로 안내하도록 지시 |

회사 정보·생활안내 442개 청크에 대한 별도 RAG 연결은 이 변경에 포함하지 않아요. 분류 연결과 모든 유형의 검색 품질 검증은 구분해요. 짧은 이어 묻기는 기존 판별 규칙에 해당할 때 직전 질문 최대 120자를 함께 분류하고, `meta.classification.usedHistory`로 알려 줘요. 후속 질문의 전반적인 품질은 별도 평가가 필요해요.

## 모델 파일과 설정

모델은 항상 `backend/models/klue_roberta_full_model.pt`에 둬요. 코드의 `MODEL_DIR`은 `backend/models/`로 고정하며 환경변수로 경로를 받지 않아요. 아래 `models/` 경로는 이 문서가 있는 `backend/` 기준이에요.

`models/`에는 사용자가 제공한 `klue_roberta_full_model.pt`, 학습 때 사용한 `config.json`·`tokenizer.json`·`tokenizer_config.json`, 해시·라벨·입력 길이를 기록한 `classifier-manifest.json`을 둬요. 토크나이저 출처와 파일 해시는 manifest에 있어요. `models/.gitattributes`는 Git 줄바꿈 변환을 끄고 JSON 원본 바이트와 해시를 보존해요. 가중치는 Git에서 제외하며 팀 공유 보관 위치는 미정이에요. 다른 PC에는 신뢰할 수 있는 경로로 같은 가중치를 별도 전달해야 해요.

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

## 연결 작업 확인 기록 (2026-10-29)

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
