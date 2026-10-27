# backend — 5차 FastAPI 백엔드 사본 (참고·로컬 실행용)

화면 개발에 필요한 API를 로컬에서 띄우기 위한 **5차 목업 백엔드 사본**이에요. 백엔드는 팀원 담당이라 여기서 기능을 고치지 않아요. 팀원 백엔드가 준비되면 `docker-compose.yml`의 `backend` 서비스(또는 `frontend/.env.local`의 `API_PROXY_TARGET`)만 바꿔 끼워요.

## 들어 있는 것

| 폴더 | 내용 |
| --- | --- |
| `app/` | FastAPI 앱(라우터·서비스·에이전트·관리자 엑셀) |
| `tools/setup_db.py` | 팀 DB 백업 복원 뒤 보조 스키마(app_ext)·보충 자료를 넣는 스크립트 |
| `db/` | 보조 스키마 SQL |
| `data/seed/` | 저장소 밖에서 받는 직원 가데이터 엑셀을 넣는 곳([안내](data/seed/README.md)) |
| `web/` | 5차 옛 화면(새 React 화면과 나란히 비교하는 용도 · <http://localhost:8815>) |

## 5차 원본과 다른 곳 (설정으로 빼기 · 공개 저장소 대응만)

| 파일 | 바꾼 것 | 이유 |
| --- | --- | --- |
| `app/auth.py` | 로그인 쿠키 이름을 `GP5_SESSION_COOKIE`로 설정(기본값은 원본과 같은 `gp5_session`) | 같은 PC·같은 브라우저에서 다른 환경과 번갈아 열 때 로그인이 서로 덮이지 않게 |
| `tools/setup_db.py` | 복원 대상 컨테이너 이름을 `COMPOSE_PROJECT_NAME`으로(기본값은 원본과 같은 `gp5`) | 고정값이면 다른 compose 프로젝트의 DB에 복원할 수 있어서 |
| `app/config.py`, `app/auth.py`(설명), `web/assets/gp-core.js`(주석) | 시연 초기 비밀번호를 코드에 적힌 기본값 없이 `.env`의 `GP5_DEMO_PASSWORD`로만 받음 | 공개 저장소에 공용 기본 비밀번호를 두지 않는 팀 원칙(`database/RESTORE.md`) |
| `tools/setup_db.py` | 시연 비밀번호가 비면 관리자 계정·직원 가데이터·팀 테스트 비밀번호 단계를 건너뜀. 직원 가데이터 엑셀이 없으면 그 단계만 건너뜀 | 비밀번호·직원 가데이터는 저장소 밖에서 받아요 |
| `app/admin_io/hr.py` | 시연 비밀번호가 비어 있으면 새 직원 추가를 막고 안내 | 빈 비밀번호로 계정이 생기지 않게 |
| `app/llm.py`, `app/regstore.py`, `app/agents/regulation.py`, `app/routers/admin.py`·`account.py`, `app/config.py`, `app/errors.py` | 규정 검색 임베딩을 RunPod-Ollama·OpenAI 모드 모두 OpenAI `text-embedding-3-small`(`OPENAI_EMBED_MODEL`)로 통일하고 `OLLAMA_EMBED_MODEL`을 없앰. OpenAI 키가 없으면 키워드로 바꾸지 않고 오류로 알림(가데이터만 키워드). 관리자 색인 만들기는 모드를 고르지 않음(받은 `provider`는 무시 · 색인 만들기는 뒤에 아래 '규정 원문 PDF' 줄에서 없앰) | 팀 합의(2026-10-26): 팀 DB 벡터가 그 모델로 만들어져 있음. 원본은 모드별 임베딩이라 Ollama 모드가 키워드 검색으로 떨어져 조항을 못 찾는 일이 있었음 |
| `app/agents/regulation.py`(`REG_SYS`) | 되묻기(`clarify`) 조건을 넓힘: 규정 질문의 뜻이 여러 가지로 읽히고 찾은 조항이 그중 일부 뜻에만 답하면 되묻기. 뜻이 분명하거나 되물은 뒤 고른 질문이면 되묻지 않음 | 원본은 '유형이 애매할 때만' 되물어서, 뜻이 갈리는 규정 질문을 모델마다 한 뜻으로 답하거나 '확인 불가'로 둠(2026-10-26 '근로 시작일' 질문) |
| `app/agents/regulation.py`(`clean_option`·`check_more`) | 되묻기 선택지는 질문만 남김(괄호 설명·첫 물음 뒤 문장을 떼고, 질문·사용자 상황에 없던 숫자가 남으면 그 선택지를 버림). '추가로 확인할 것'(more) 문장도 숫자 검사: 근거에 없는 숫자면 이번에 넘긴 조항 중 그 숫자가 있는 조항을 근거에 더하고, 없으면 문장을 버림. 규정 이름+조 번호로 가리킨 조항도 근거에 넣음. 지시문에도 같은 규칙을 적음 | 원본은 요약·적용 문장만 숫자를 검사해서, 선택지·more에 확인 안 된 숫자가 들어가거나 more에 쓴 조항이 '규정 근거 보기'에 빠짐(2026-10-26 '급여 지급일 21일' · '별표 1에 1일') |
| `app/agents/runtime.py`, `app/routers/account.py`, `app/services/goals.py` | '에이전트 동작 보기'(`GET /ai/log`)가 본인 호출 대신 모든 계정의 호출을 줌(직원·관리자 계정 모두). 기록마다 누구의 일인지(`employee`)와 관리자 화면에서 시작했는지(`by`)를 붙이고, 시각은 설정 시간대(`GP5_DB_TIMEZONE`)로 적음 | 시연·디버그 전용 기능이라 누가 호출했든 다 보이게(2026-10-26 사용자 결정 · 운영에서는 아무도 쓰지 않음 → B-1로 꺼야 함) · 컨테이너 시계가 UTC라 기록 시각이 9시간 어긋났음 |
| `app/routers/admin.py`, `app/services/goals.py` | 관리자 목표 후보 다시 만들기에 모델 고르기(`mode`: `ollama`·`openai` 추가 · 이번 작업에만 쓰고 직원이 고른 AI 모드는 바꾸지 않음)와 직원 고르기(`employeeIds` · 새 `GET /admin/goal-suggestions/employees`) 추가 | 관리자가 모델을 정해 일괄로, 또는 몇 명만 골라 다시 만들 수 있게(2026-10-26 사용자 요청) · 원본은 가데이터 / 각 직원의 모드 두 가지로 재직 직원 전체만 |
| `app/errors.py` | Ollama 401·403을 '키 문제(auth)'로 분류하고 `OLLAMA_API_KEY` 넣는 법을 조치로 안내(원본은 '잠시 뒤 다시 시도') | Pod 앞 nginx가 키를 확인하는 구성(RunPod Pod 연결 절차는 담당자 안내)에서 원인이 바로 보이게 (2026-10-26) |
| `app/config.py`, `app/llm.py`, `app/errors.py` | `OLLAMA_MODEL` 코드 기본값(`qwen3.5:9b`)을 없앰. 비우면 RunPod-Ollama 모드를 '쓸 수 없음 · .env에 OLLAMA_MODEL이 없어요'로 보여 줌 | Pod에 받아 둔 모델만 쓸 수 있어 기본 이름이 의미 없음 · 모델은 `.env`에서만 정하게 (2026-10-26) |
| `app/config.py`, `app/llm.py` | Ollama 생각(thinking) 모드를 `.env`의 `OLLAMA_THINK`(on/off)로 정함. 비우면 원본처럼 `think`를 보내지 않음 | 생각 모드가 기본으로 켜진 모델(qwen3.8:27b)은 답 앞에 생각을 길게 써서 느림 · 끌 수 있게 (2026-10-26) |
| `app/regfiles.py`(새 파일), `app/routers/admin.py`, `app/admin_io/`(`regulations.py` 지움), `app/regstore.py`(설명), `app/config.py`, `db/02_app_ext.sql`, `docker-compose.yml` | 관리자의 규정 관리를 **원문 PDF 올리기·내려받기**로 바꿈. 규정·조항 엑셀/CSV·한 건 고치기(`/admin/datasets/regulations/*`)와 규정 색인 만들기(`POST /admin/regulations/index`)를 없애고, 지금 규정 목록(`GET /admin/regulations`)·원문 PDF 내려받기(`GET /admin/regulations/{id}/pdf`)·새 규정 PDF 올리기(`POST /admin/regulations/uploads`, 파일+메모)·올린 PDF 목록/내려받기·잘못 올린 PDF 삭제(`DELETE /admin/regulations/uploads/{id}` · 파일과 기록을 함께 지움)를 추가. 지금 규정 원문은 팀 규정 묶음의 `source/`(`GP5_REGULATION_FILES_DIR` · compose 는 `team_db/regulations` 를 읽기 전용으로 붙임), 올린 PDF는 `var/uploads/regulations/` 와 `app_ext.regulation_uploads`(처리 상태 없음). 개요 응답의 `regulations` 를 PDF 개수로 바꾸고 `providers` 를 맨 위로 옮김. 옛 화면(`web/`)의 규정 데이터 메뉴는 이제 동작하지 않음 | 사용자 결정(2026-10-26): 규정은 벡터 DB를 거친 RAG에 쓰여 관리자가 고치지 않고, 시스템 관리자(서비스 운영팀)가 올라온 PDF를 내려받아 임베딩·벡터 DB를 갱신(MVP 방식). 조항 표는 원문과 맞춰 보기 어려워 원문 PDF로 보게 함 |

나머지는 5차 원본의 `app`·`tools`·`db`·`web`과 같아요(2026-10-26 비교).

`data/seed/`의 직원 가데이터 엑셀과 ERD 사본은 저장소에 올리지 않아요([data/seed/README.md](data/seed/README.md)). ERD 원본은 팀 저장소 `docs/07_데이터베이스_저장소_설계/ERD_최종.html`에 있어요.

## 실행

보통은 맨 위 폴더에서 Docker로 켜요(DB·복원·보충 자료가 함께 돌아요).

```bash
docker compose up -d backend
```

- API 문서: <http://localhost:8815/api/docs>
- 설정은 맨 위의 `.env` 하나를 읽어요(`.env.example` 참고).

파이썬으로 직접 띄울 때(선택 · Python 3.12 · 이번 작업에서는 확인하지 않은 방법): 이 폴더에서 패키지를 설치하고, 맨 위 `.env`를 `GP5_ENV_FILE`로 알려 준 뒤 실행해요(앱은 기본으로 이 폴더의 `.env`를 읽어요). DB는 Docker의 `db` 서비스를 그대로 써요(`.env`의 `GP5_DB_PORT`). 도커의 `backend`와 같은 8815를 쓰므로 둘 중 하나만 켜요.

```bash
pip install -r requirements.txt
```

```bash
GP5_ENV_FILE=../.env python -m uvicorn app.main:app --port 8815
```

PowerShell에서는 `$env:GP5_ENV_FILE = '../.env'`를 먼저 실행한 뒤 `python -m uvicorn app.main:app --port 8815`를 실행해요.

## 고칠 것이 보이면

여기서 고치지 말고 GitHub 이슈로 백엔드 담당에게 넘겨요. 화면이 기대하는 모양은 [API 계약](../frontend/docs/API_계약.md)에 있어요.
