# backend — 5차 FastAPI 백엔드 사본 (참고·로컬 실행용)

화면 개발에 필요한 API를 로컬에서 띄우기 위한 **5차 목업 백엔드 사본**이에요. 팀원 백엔드가 준비되면 `docker-compose.yml`의 `backend` 서비스(또는 `frontend/.env.local`의 `API_PROXY_TARGET`)만 바꿔 끼워요. 2026-10-29 사용자 요청으로 이 사본의 챗봇에 로컬 RoBERTa 질문 분류를 연결했어요. 팀원 백엔드에도 반영됐다는 뜻은 아니에요.

## 들어 있는 것

| 폴더 | 내용 |
| --- | --- |
| `app/` | FastAPI 앱(라우터·서비스·에이전트·관리자 엑셀) |
| `tools/setup_db.py` | 팀 DB 백업 복원 뒤 보조 스키마(app_ext)·보충 자료를 넣는 스크립트 |
| `db/` | 보조 스키마 SQL |
| `web/` | 5차 옛 화면(새 React 화면과 나란히 비교하는 용도 · <http://localhost:8815>) |

## 5차 원본과 다른 곳 (설정으로 빼기 · 공개 저장소 대응만)

| 파일 | 바꾼 것 | 이유 |
| --- | --- | --- |
| `app/auth.py` | 로그인 쿠키 이름을 `GP5_SESSION_COOKIE`로 설정(기본값은 원본과 같은 `gp5_session`) | 같은 PC·같은 브라우저에서 다른 환경과 번갈아 열 때 로그인이 서로 덮이지 않게 |
| `tools/setup_db.py` | 복원 대상 컨테이너 이름을 `COMPOSE_PROJECT_NAME`으로(기본값은 원본과 같은 `gp5`) | 고정값이면 다른 compose 프로젝트의 DB에 복원할 수 있어서 |
| `app/config.py`, `app/auth.py`(설명), `web/assets/gp-core.js`(주석) | 시연 초기 비밀번호를 코드에 적힌 기본값 없이 `.env`의 `GP5_DEMO_PASSWORD`로만 받음 | 공개 저장소에 공용 기본 비밀번호를 두지 않는 팀 원칙(`database/RESTORE.md`) |
| `tools/setup_db.py` | 시연 비밀번호가 비면 관리자 계정·팀 시험 비밀번호 단계를 건너뜀 | 비밀번호는 저장소 밖에서 정해요 |
| `app/admin_io/hr.py` | 시연 비밀번호가 비어 있으면 새 직원 추가를 막고 안내 | 빈 비밀번호로 계정이 생기지 않게 |
| `app/llm.py`, `app/regstore.py`, `app/agents/regulation.py`, `app/routers/admin.py`·`account.py`, `app/config.py`, `app/errors.py` | 규정 검색 임베딩을 RunPod-Ollama·OpenAI 모드 모두 OpenAI `text-embedding-3-small`(`OPENAI_EMBED_MODEL`)로 통일하고 `OLLAMA_EMBED_MODEL`을 없앰. OpenAI 키가 없으면 키워드로 바꾸지 않고 오류로 알림(가데이터만 키워드). 관리자 색인 만들기는 모드를 고르지 않음(받은 `provider`는 무시 · 색인 만들기는 뒤에 아래 '규정 원문 PDF' 줄에서 없앰) | 팀 합의(2026-10-26): 팀 DB 벡터가 그 모델로 만들어져 있음. 원본은 모드별 임베딩이라 Ollama 모드가 키워드 검색으로 떨어져 조항을 못 찾는 일이 있었음 |
| `app/agents/regulation.py`(`REG_SYS`) | 되묻기(`clarify`) 조건을 넓힘: 규정 질문의 뜻이 여러 가지로 읽히고 찾은 조항이 그중 일부 뜻에만 답하면 되묻기. 뜻이 분명하거나 되물은 뒤 고른 질문이면 되묻지 않음 | 원본은 '유형이 애매할 때만' 되물어서, 뜻이 갈리는 규정 질문을 모델마다 한 뜻으로 답하거나 '확인 불가'로 둠(2026-10-26 '근로 시작일' 질문) |
| `app/agents/regulation.py`(`clean_option`·`check_more`) | 되묻기 선택지는 질문만 남김(괄호 설명·첫 물음 뒤 문장을 떼고, 질문·사용자 상황에 없던 숫자가 남으면 그 선택지를 버림). '추가로 확인할 것'(more) 문장도 숫자 검사: 근거에 없는 숫자면 이번에 넘긴 조항 중 그 숫자가 있는 조항을 근거에 더하고, 없으면 문장을 버림. 규정 이름+조 번호로 가리킨 조항도 근거에 넣음. 지시문에도 같은 규칙을 적음 | 원본은 요약·적용 문장만 숫자를 검사해서, 선택지·more에 확인 안 된 숫자가 들어가거나 more에 쓴 조항이 '규정 근거 보기'에 빠짐(2026-10-26 '급여 지급일 21일' · '별표 1에 1일') |
| `app/agents/runtime.py`, `app/routers/account.py`, `app/services/goals.py` | '에이전트 동작 보기'(`GET /ai/log`)가 본인 호출 대신 모든 계정의 호출을 줌(직원·관리자 계정 모두). 기록마다 누구의 일인지(`employee`)와 관리자 화면에서 시작했는지(`by`)를 붙이고, 시각은 설정 시간대(`GP5_DB_TIMEZONE`)로 적음 | 시연·디버그 전용 기능이라 누가 호출했든 다 보이게(2026-10-26 사용자 결정 · 운영에서는 아무도 쓰지 않음 → B-1로 꺼야 함) · 컨테이너 시계가 UTC라 기록 시각이 9시간 어긋났음 |
| `app/routers/admin.py`, `app/services/goals.py` | 관리자 목표 후보 다시 만들기에 모델 고르기(`mode`: `ollama`·`openai` 추가 · 이번 작업에만 쓰고 직원이 고른 AI 모드는 바꾸지 않음)와 직원 고르기(`employeeIds` · 새 `GET /admin/goal-suggestions/employees`) 추가 | 관리자가 모델을 정해 일괄로, 또는 몇 명만 골라 다시 만들 수 있게(2026-10-26 사용자 요청) · 원본은 가데이터 / 각 직원의 모드 두 가지로 재직 직원 전체만 |
| `app/errors.py` | Ollama 401·403을 '키 문제(auth)'로 분류하고 `OLLAMA_API_KEY` 넣는 법을 조치로 안내(원본은 '잠시 뒤 다시 시도') | Pod 앞 nginx가 키를 확인하는 구성(RunPod Pod 연결 절차는 [RunPod_Ollama_연결_절차.md](RunPod_Ollama_연결_절차.md))에서 원인이 바로 보이게 (2026-10-26) |
| `app/config.py`, `app/llm.py`, `app/errors.py` | RunPod-Ollama 기본 모델을 팀 모델로 둠(`app/config.py`의 `OLLAMA_TEAM_*`): 진단·로드맵 `growpath-27b`, 규정 에이전트 `growpath-regulation-4b`, 비전 없음. `.env`의 `OLLAMA_MODEL`·`OLLAMA_MODEL_REGULATION`·`OLLAMA_VISION_MODEL`은 비워 두면 기본값이고 원본 Qwen과 비교할 때만 적음. `OLLAMA_MODEL_ROADMAP`은 없앰(로드맵은 `OLLAMA_MODEL`과 같은 모델). `OLLAMA_BASE_URL`만 있으면 RunPod-Ollama 모드를 쓸 수 있음 | 팀 결정(2026-10-29 · #33): RunPod-Ollama는 팀이 파인튜닝한 두 모델을 기본으로 씀(이름은 Pod에서 만드는 별칭 · [RunPod_Ollama_연결_절차.md](RunPod_Ollama_연결_절차.md) 2-4). 원본(5차)은 `OLLAMA_MODEL` 기본 `qwen3.5:9b`, 그전(2026-10-26)에는 기본값 없이 `.env`로만 정했음 |
| `app/config.py`, `app/llm.py` | Ollama 생각(thinking) 모드를 `.env`의 `OLLAMA_THINK`(on/off)로 정함. 비우면 원본처럼 `think`를 보내지 않음 | 생각 모드가 기본으로 켜진 모델(qwen3.8:27b)은 답 앞에 생각을 길게 써서 느림 · 끌 수 있게 (2026-10-26) |
| `app/llm.py`, `app/agents/regulation.py`, `app/routers/account.py`, `tools/mock_ollama.py`·`mock_ollama.env` | 규정 에이전트(사내 생활 도우미 답변·안별 지원 조건 확인)가 `regulation` 역할로 규정 모델(기본 `growpath-regulation-4b`)을 부름. 연결 확인(`GET /ai/status`)이 그 모델의 설치·GPU 적재 여부도 보고, `GET /ai/providers`의 `models`에 `regulation`을 더함. 모의 Ollama 모델 이름을 팀 모델 이름으로 바꾸고 `no-regulation-model` 시나리오를 추가(`no-roadmap-model`은 로드맵이 진단과 같은 모델이 돼 없앰) | 팀 논의(2026-10-29 · #33): 진단·로드맵은 팀원이 파인튜닝한 27b, 규정 에이전트는 팀원이 파인튜닝한 4b를 한 Pod에 함께 올려 씀. 원본은 로드맵만 모델을 따로 정할 수 있었음 |
| `db/02_app_ext.sql`, `app/config.py`, `app/routers/account.py`, `app/agents/runtime.py`, `app/llm.py`, `app/services/goals.py`, `app/errors.py`, `tools/mock_ollama.py` | 직원이 좌측 'AI 모델'에서 모드별 **추론 정도**를 고름(#28): `app_ext.user_settings.reasoning`(jsonb `{ollama, openai}` · 없는 모드는 `.env` 기본값)·`PUT /me/reasoning` 추가, `GET /me`에 `reasoning`. RunPod-Ollama는 진단·로드맵 모델에만 쓰고, 연결 확인(`/ai/status`) 때 그 모델의 `/api/show` `thinking.values`로 고를 단계를 알아내 `models[].think`로 줌 · `think`(on/off는 true/false, 나머지는 단계 이름)로 보냄. **규정 에이전트 모델은 직원 값·`.env`와 관계없이 늘 `think: false`**(`config.OLLAMA_REGULATION_THINK`). OpenAI는 받는 단계 안에서 골라 `reasoning_effort`로 보냄: 기본 모델 gpt-6-luna는 코드의 확인한 단계(none~xhigh)·모델 기본값(medium · 화면 '기본값 · 보통'), 다른 모델은 `.env`의 `OPENAI_REASONING_LEVELS`(기본값 `OPENAI_REASONING_EFFORT` · `GET /ai/providers`의 `reasoning`의 `levels`·`default`·`modelDefault` · `OPENAI_MODEL`이 아닌 비전 모델에는 보내지 않음). 이미지 읽기 모델에는 직원 값을 쓰지 않음. `OLLAMA_THINK`는 진단·로드맵 모델 기본값이 되고 단계 이름도 받음(true·false 같은 값은 예전처럼 시작할 때 멈춤). 관리자가 모델을 골라 목표 후보를 다시 만들 때는 `.env` 값을 씀. 생각 모드·`reasoning_effort`를 받지 않는다는 오류에 원인 문구를 붙임. 모의 Ollama에 모델별 `/api/show`(`--think` · 기본은 실제 Pod 값)·`--host` 추가 | 모델마다 받는 단계가 다르고(팀 27b: 끔·low·medium·xhigh — RunPod 연결 절차의 실제 Pod 기록 · gpt-6-luna Chat Completions: none~xhigh, 모델 문서의 max는 400) `.env`를 고치고 서버를 다시 켜지 않아도 화면에서 바꿔 보게. 규정 에이전트 모델(4b)은 생각을 끄고 학습해 추론 없이가 기본이고 사용자가 바꾸면 안 됨 (2026-10-28·29 사용자 요청·결정) |
| `app/regfiles.py`(새 파일), `app/routers/admin.py`, `app/admin_io/`(`regulations.py` 지움), `app/regstore.py`(설명), `app/config.py`, `db/02_app_ext.sql`, `docker-compose.yml` | 관리자의 규정 관리를 **원문 PDF 올리기·내려받기**로 바꿈. 규정·조항 엑셀/CSV·한 건 고치기(`/admin/datasets/regulations/*`)와 규정 색인 만들기(`POST /admin/regulations/index`)를 없애고, 지금 규정 목록(`GET /admin/regulations`)·원문 PDF 내려받기(`GET /admin/regulations/{id}/pdf`)·새 규정 PDF 올리기(`POST /admin/regulations/uploads`, 파일+메모)·올린 PDF 목록/내려받기·잘못 올린 PDF 삭제(`DELETE /admin/regulations/uploads/{id}` · 파일과 기록을 함께 지움)를 추가. 지금 규정 원문은 팀 규정 묶음의 `source/`(`GP5_REGULATION_FILES_DIR` · compose 는 `team_db/regulations` 를 읽기 전용으로 붙임), 올린 PDF는 `var/uploads/regulations/` 와 `app_ext.regulation_uploads`(처리 상태 없음). 개요 응답의 `regulations` 를 PDF 개수로 바꾸고 `providers` 를 맨 위로 옮김. 옛 화면(`web/`)의 규정 데이터 메뉴는 이제 동작하지 않음 | 사용자 결정(2026-10-26): 규정은 벡터 DB를 거친 RAG에 쓰여 관리자가 고치지 않고, 시스템 관리자(서비스 운영팀)가 올라온 PDF를 내려받아 임베딩·벡터 DB를 갱신(MVP 방식). 조항 표는 원문과 맞춰 보기 어려워 원문 PDF로 보게 함 |

나머지는 5차 원본의 `app`·`tools`·`db`·`web`과 같아요(2026-10-26 비교).

### 팀 최신 DB(#22) 기준으로 맞춘 곳 (2026-10-27 사용자 결정: 무조건 최신 DB 기준)

| 파일 | 바꾼 것 | 이유 |
| --- | --- | --- |
| `tools/setup_db.py`, `Dockerfile` | 직원 가데이터 엑셀(2.9.0) 단계와 `data/seed/` 폴더를 없앰. 기본 백업을 `team_db/growpath_latest.dump`로 | 최신 백업에 시험 직원 100명·부서장 5명·스킬·자격·학력이 들어 있고, 예전 가데이터 16명은 부서장 중복(`employees_one_department_head`)으로 들어가지 않음 |
| `tools/setup_db.py` | 시험 비밀번호(로컬 사본만)를 사번이 있는 계정에만 넣음 | 사번 없는 `REAL_USER` 행은 로그인할 수 없고, 새 사번 필수 제약(`employees_number_required` · NOT VALID)이 그 행의 어떤 수정도 막음 |
| `app/services/profile.py` | 내 정보의 본인 입력을 팀 표에서 읽고 씀: 경험 요약·개발 경력·사용 기술·프로젝트·교육은 `employee_input_profiles`, 자격은 `employee_certifications`(팀 자격표에 있는 이름) + `employees.unlisted_certifications`(없는 이름). 본인 입력 전에는 보유 스킬(`employee_skills`)을 사용 기술 처음 값으로 보여 줌. 팀 표에 자리가 없는 업무 설명·없음 확인과 되돌리기용 처음 값만 `app_ext.employee_self_inputs`에. 학력 단계 코드는 한글로 | 팀 직원 입력 양식(`database/src/database/employee_form.py`)과 같은 표·열에 저장 · API 모양(API-06)은 그대로 |
| `app/services/profile.py`, `app/admin_io/hr.py` | 입사일·현재 근무 시작일을 `employees.hire_date`·`department_start_date`에서 읽고 관리자 인적 데이터 반영도 그 열에 씀. 직원 구분이 비면 직급 이름('일반직 4급')의 앞부분 | 최신 DB 에 생긴 열 · 직원 구분은 규정 묶음 선택에 씀 |

### PR #23 리뷰로 고친 곳 (2026-10-27)

| 파일 | 바꾼 것 | 이유 |
| --- | --- | --- |
| `app/services/profile.py`(`team_view`), `app/services/plans.py` | 부서장 직원 목록·상세의 직원 정보를 이름·사번·소속·직급·직위·부서장 여부만 보냄 | 원본은 내 정보 전체(평정·본인 입력·학력 등)를 보내 화면에서 숨겨도 응답으로 받을 수 있었음(설계서 공개 범위) |
| `app/services/plans.py`(`reports`) | 부서장 보고서에서 목표 달성 답(`goalSelf`)·결과물 첨부(`file`)를 뺌 | 사후 점검 원본 응답·첨부 비공개(부서장 로드맵 기록에서는 이미 뺐음) |
| `app/routers/work.py`(첨부 올리기) | 본인의 진행 중 로드맵인지, 그 로드맵의 활동(또는 사후 점검 `post`)인지 먼저 확인 | 원본은 로그인만 확인하고 없는·남의 로드맵에도 파일을 저장했음 |
| `app/services/plans.py`(`_base_rows`) | 주소의 로드맵 id 모양이 틀리면 404 | 원본은 DB 형 변환 오류로 500 |

### 부서장 범위 (2026-10-27 팀 합의)

| 파일 | 바꾼 것 | 이유 |
| --- | --- | --- |
| `app/services/profile.py`(`members_of`·`supervisor_of`) | 부서장은 자기 부서 직원만 봄. 부서장의 계획은 본인만 봄(상위 부서장이 보지 않음). 상위 부서는 내 정보 소속 표시·목표 후보 입력·관리자 편집에 그대로 씀 | 팀 DB `employee_can_read_employee`(본인 또는 같은 부서의 부서장)와 같게. 원본은 바로 아래 부서의 부서장까지 봐서, 새 DB 에서는 그 코멘트가 DB 트리거에 막혀 500 |
| `app/services/plans.py`(수정안 확정·지원 조건 확인) | 코멘트 작성자가 둘 이상이면 새 버전 저장을 409로 막던 것을 없앰 | 새 DB 에서 코멘트 '수정 완료' 표시는 작성자 검사 트리거(본문·작성자·로드맵 열에만 걸림)를 거치지 않음 |

ERD 원본은 팀 저장소 `docs/07_데이터베이스_저장소_설계/ERD_최종.html`에 있어요.

## 실행

보통은 맨 위 폴더에서 Docker로 켜요(DB·복원·보충 자료가 함께 돌아요).

```bash
docker compose up -d backend
```

- API 문서: <http://localhost:8815/api/docs>
- 설정은 맨 위의 `.env` 하나를 읽어요(`.env.example` 참고).

파이썬으로 직접 띄울 때(선택 · Python 3.12 · 이번 작업에서는 확인하지 않은 방법): 이 폴더에서 패키지를 설치하고, 맨 위 `.env`를 `GP5_ENV_FILE`로 알려 준 뒤 실행해요(앱은 기본으로 이 폴더의 `.env`를 읽어요). DB는 Docker의 `db` 서비스를 그대로 써요(`.env`의 `GP5_DB_PORT`). 도커의 `backend`와 같은 8815를 쓰므로 둘 중 하나만 켜요.

```bash
pip install -r ../requirements.txt
```

```bash
GP5_ENV_FILE=../.env python -m uvicorn app.main:app --port 8815
```

PowerShell에서는 `$env:GP5_ENV_FILE = '../.env'`를 먼저 실행한 뒤 `python -m uvicorn app.main:app --port 8815`를 실행해요.

분류 모델 연결 흐름·파일별 역할·실행 방법·검증 기록은 [챗봇 질문 분류 안내](classification.md)를 참고하세요.

## 고칠 것이 보이면

추가 변경은 GitHub 이슈로 백엔드 담당과 조율해요. 화면이 기대하는 모양은 [API 계약](../frontend/docs/API_계약.md)에 있어요.
