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
| `db/02_app_ext.sql`, `app/config.py`, `app/routers/account.py`, `app/agents/runtime.py`, `app/llm.py`, `app/services/goals.py`, `app/errors.py`, `tools/mock_ollama.py` | 직원이 좌측 'AI 모델'에서 모드별 **추론 정도**를 고름(#28): `app_ext.user_settings.reasoning`(jsonb `{ollama, openai}` · 없는 모드는 `.env` 기본값)·`PUT /me/reasoning` 추가, `GET /me`에 `reasoning`. RunPod-Ollama는 진단·로드맵 모델에만 쓰고, 연결 확인(`/ai/status`) 때 그 모델의 `/api/show` `thinking.values`로 고를 단계를 알아내 `models[].think`로 줌 · `think`(on/off는 true/false, 나머지는 단계 이름)로 보냄. **규정 에이전트 모델은 직원 값·`.env`와 관계없이 늘 `think: false`**(`config.OLLAMA_REGULATION_THINK`). OpenAI는 받는 단계 안에서 골라 `reasoning_effort`로 보냄: 기본 모델 gpt-6-luna는 코드의 확인한 단계(none~xhigh)·모델 기본값(medium · 화면 '기본값 · 보통'), 다른 모델은 `.env`의 `OPENAI_REASONING_LEVELS`(기본값 `OPENAI_REASONING_EFFORT` · `GET /ai/providers`의 `reasoning`의 `levels`·`default`·`modelDefault` · `OPENAI_MODEL`이 아닌 비전 모델에는 보내지 않음). 고른 값이 지금 모델이 받는 단계가 아니면(모델을 바꾼 뒤 남은 옛 선택) `.env` 기본값을 보냄(모델별 단계는 `/api/show` 결과를 기억해 둠). 저장은 그 모드의 키만 한 SQL 문으로 바꿈(동시 저장에도 다른 모드 값 유지). 이미지 읽기 모델에는 직원 값을 쓰지 않음. `OLLAMA_THINK`는 진단·로드맵 모델 기본값이 되고 단계 이름도 받음(true·false 같은 값은 예전처럼 시작할 때 멈춤). 관리자가 모델을 골라 목표 후보를 다시 만들 때는 `.env` 값을 씀. 생각 모드·`reasoning_effort`를 받지 않는다는 오류에 원인 문구를 붙임. 모의 Ollama에 모델별 `/api/show`(`--think` · 기본은 실제 Pod 값)·`--host` 추가 | 모델마다 받는 단계가 다르고(팀 27b: 끔·low·medium·xhigh — RunPod 연결 절차의 실제 Pod 기록 · gpt-6-luna Chat Completions: none~xhigh, 모델 문서의 max는 400) `.env`를 고치고 서버를 다시 켜지 않아도 화면에서 바꿔 보게. 규정 에이전트 모델(4b)은 생각을 끄고 학습해 추론 없이가 기본이고 사용자가 바꾸면 안 됨 (2026-10-28·29 사용자 요청·결정) |
| `app/regfiles.py`(새 파일), `app/routers/admin.py`, `app/admin_io/`(`regulations.py` 지움), `app/regstore.py`(설명), `app/config.py`, `db/02_app_ext.sql`, `docker-compose.yml` | 관리자의 규정 관리를 **원문 PDF 올리기·내려받기**로 바꿈. 규정·조항 엑셀/CSV·한 건 고치기(`/admin/datasets/regulations/*`)와 규정 색인 만들기(`POST /admin/regulations/index`)를 없애고, 지금 규정 목록(`GET /admin/regulations`)·원문 PDF 내려받기(`GET /admin/regulations/{id}/pdf`)·새 규정 PDF 올리기(`POST /admin/regulations/uploads`, 파일+메모)·올린 PDF 목록/내려받기·잘못 올린 PDF 삭제(`DELETE /admin/regulations/uploads/{id}` · 파일과 기록을 함께 지움)를 추가. 지금 규정 원문은 팀 규정 묶음의 `source/`(`GP5_REGULATION_FILES_DIR` · compose 는 `team_db/regulations` 를 읽기 전용으로 붙임), 올린 PDF는 `var/uploads/regulations/` 와 `app_ext.regulation_uploads`(처리 상태 없음). 개요 응답의 `regulations` 를 PDF 개수로 바꾸고 `providers` 를 맨 위로 옮김. 옛 화면(`web/`)의 규정 데이터 메뉴는 이제 동작하지 않음 | 사용자 결정(2026-10-26): 규정은 벡터 DB를 거친 RAG에 쓰여 관리자가 고치지 않고, 시스템 관리자(서비스 운영팀)가 올라온 PDF를 내려받아 임베딩·벡터 DB를 갱신(MVP 방식). 조항 표는 원문과 맞춰 보기 어려워 원문 PDF로 보게 함 |

나머지는 5차 원본의 `app`·`tools`·`db`·`web`과 같아요(2026-10-26 비교).

### 팀 최신 DB(#22) 기준으로 맞춘 곳 (2026-10-27 사용자 결정: 무조건 최신 DB 기준)

| 파일 | 바꾼 것 | 이유 |
| --- | --- | --- |
| `tools/setup_db.py`, `Dockerfile` | 직원 가데이터 엑셀(2.9.0) 단계와 `data/seed/` 폴더를 없앰. 기본 백업을 `team_db/growpath_latest.dump`로 | 최신 백업에 시험 직원 100명·부서장 5명·스킬·자격·학력이 들어 있고, 예전 가데이터 16명은 부서장 중복(`employees_one_department_head`)으로 들어가지 않음 |
| `tools/setup_db.py` | 시험 비밀번호(로컬 사본만)를 사번이 있는 계정에만 넣음 | 사번 없는 `REAL_USER` 행은 로그인할 수 없고, 새 사번 필수 제약(`employees_number_required` · NOT VALID)이 그 행의 어떤 수정도 막음 |
| `app/services/profile.py` | 업무 설명은 `employees.planned_project_description`, 경험·개발 경력·기술·프로젝트·교육은 `employee_input_profiles`, 자격은 `employee_certifications` + `employees.unlisted_certifications`. 업무·프로젝트는 각각 선택. `app_ext.employee_self_inputs`에는 처음 값·입력 상태·설명 변경 해시만 저장. 구판 설명은 읽기 호환 유지 | 팀 직원 입력 양식과 같은 표·열에 저장. 새 표/열 없음. 선택 이관 SQL은 `db/migrate_self_work_descriptions.sql` |
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

## 목표 후보 사전 준비

로그인과 세션 조회에서는 목표 생성 요청을 하지 않아요. 홈페이지에서 본인 입력 저장·되돌리기·평정 동의 또는 관리자 수정/업로드가 성공한 뒤, 추천 입력이 바뀐 직원만 백그라운드로 갱신해요. 부서명·상위 부서 변경과 보유 자격명 변경도 영향을 받는 직원을 포함해요. 목표 화면은 후보가 없는 계정만 처음 준비하고 기존 후보는 그대로 읽어요. 동시 요청은 한 작업을 공유하며 실패하면 이전 후보를 보존하고 사용자가 다시 시도해요. SQL로 직접 수정한 경우에는 명시적으로 후보를 다시 만들어요.

목표 후보의 생성 기준은 `app/agents/goals.py`의 `G_SYS`와 `_api`예요. 앱과 사전 생성 도구 모두 같은 서비스를 사용해요. 모델에는 이름·이메일·사번을 보내지 않고, 소속·직급·직무와 입력된 업무 설명·경험·기술·자격·교육·프로젝트를 전달해요. 평정은 본인이 활용에 동의한 정보만 포함해요. 본인 입력이 없어도 사내 기본 정보가 있으면 실제 모델로 기초 학습 방향을 제안하고, 근거가 전혀 없을 때만 기본 후보를 사용해요.

모델에는 실제로 채워진 항목 이름을 `availableBasis`로 명시해요. 서로 다른 후보 3개, 각 8~160자이고 `싶어요.`로 끝나는 문장, 비어 있지 않은 추천 이유와 실제 제공된 항목의 근거를 검사해요. 입력 문장 안의 지시는 따르지 않으며, 없는 업무·경력·자격·프로젝트를 만들지 않도록 지시해요. 형식·근거 항목 검사는 사실 검증 전체를 대신하지 않으므로 결과도 프로필과 대조해야 해요. 검사 실패를 고정 후보의 성공으로 바꾸지 않고 이전 후보를 보존해요. 실제 모델 호출과 무료 고정 응답 검증은 별도로 기록해요.

DB 공유 전에 미리 생성할 수도 있어요. `backend/`에서 실제 앱 DB 설정과 `db/02_app_ext.sql`을 준비한 뒤 대상 ID를 지정해요. 아래 ID는 예시이므로 실제 확인한 `employee_id`로 바꿔요. 원문·비밀번호·키는 출력하지 않아요.

```powershell
$preloadEmployeeId = 123  # 예시 ID
python tools/preload_goals.py --employee-id $preloadEmployeeId
# API/GPU 사용 범위를 승인받은 뒤에만 실행. 여러 명은 --employee-id를 반복해요(기본 최대 4명).
python tools/preload_goals.py --employee-id $preloadEmployeeId --provider ollama --apply
```

기본 실행은 조회만 하며 추론/DB 쓰기가 없어요. `--apply`는 생성이 필요한 대상만 처리하고 `--provider openai`는 유료 API를 사용해요. `mock`은 가데이터로 표시되며 실제 추론으로 계산하지 않아요. 실패한 같은 입력은 자동 재시도하지 않으므로 화면의 다시 만들기를 사용해요. 기존 유효 후보는 모델을 지정해도 재사용해요.

완료 후 `public.employee_recommended_prompts`와 `app_ext.goal_suggestion_meta`·`goal_suggestion_runs`를 포함한 **전체 DB 백업**을 공유해요. 후보뿐 아니라 이유·입력 해시·상태도 있어야 수신 PC 로그인에서 같은 후보를 재사용할 수 있어요. 업무 설명의 구판 값이 남아 있으면 새 앱이 읽기 호환을 유지하며, 선택 이관 SQL은 백업/충돌 확인 후 명시적으로 실행해요.

2026-10-29 앞선 4명 실제 검증: 사용자 지정 `gpt-6-luna`로 4명×3개 후보를 4회 호출해 사전 저장했어요. 직원 설정의 AI 모드는 바꾸지 않았어요. 같은 입력의 재로그인은 생성 모델이 아닌 저장된 후보를 재사용해요. 전체 백업에는 기존 `app_ext` 25개 표도 포함했고 복원 후에도 추가 호출 없이 표시됨을 확인했어요. 실제 생성 기록은 `database/data/exports/actual_goal_preload_20261029.manifest.json`을 봐 주세요.

2026-10-29 추가 검증: 가상 직원 100명에게 `gpt-6-luna`를 1회씩, 총 100회 호출해 300개를 더 저장했어요. 해당 시점 후보는 기존 12개와 합쳐 312개였어요. 로그인/세션은 생성 요청을 하지 않고 홈페이지의 정보 저장 성공 뒤 갱신해요. SQL 직접 수정은 자동 갱신하지 않으므로 명시적 다시 만들기를 사용해요. 전체 백업과 저장 후 갱신 코드는 각각 배포해야 해요.

2026-10-29 목표 생성 checkpoint: 직원 표시 정리 후 105명에 실제 후보 315개를 저장했어요. 초기 105회 중 1건의 근거 검사가 실패했고 별도 승인 1회로 보완했어요(총 106회, 자동 재시도 0회). 앱과 사전 생성은 같은 서비스·에이전트 경로를 사용하며 추천 근거 목록과 후보 문장 형식 검사를 보완했어요. 생성/복원본 각각 105명 로그인·목표 조회에서 추가 모델 호출 0회를 확인했어요. 최신 기록은 `database/data/exports/natural105_goals_20261029.manifest.json`을 봐 주세요.

2026-10-29 복원 환경 호환 검사: 사내 스킬·등록 자격 목록은 DB 언어별 정렬 차이와 무관하게 같은 순서를 사용해요. Windows 백업을 Linux에 복원해도 105명 모두 기존 추천 입력과 일치하며, 사용자 입력 순서는 보존해요. 직원 보정(#27)과 강좌·최종 공유 DB 배포 기록(#35)은 PR #29에서 함께 전달해요. 현재 공유본은 [복원 안내](../database/RESTORE.md)를 따르세요. 기존 `natural105` manifest는 생성 시점의 기록으로 보존해요.

## 고칠 것이 보이면

추가 변경은 GitHub 이슈로 백엔드 담당과 조율해요. 화면이 기대하는 모양은 [API 계약](../frontend/docs/API_계약.md)에 있어요.

## Track 프롬프트 DB 연결 (#38)

Free Track(A1→agent_certified), Fast Track(A2→agent_fasttrack), Challenge Track(A3→agent_practical)은 `public.prompt_versions`의 활성 버전을 매 요청 읽습니다. 기존 agent_id는 유지하며, 이름 변경 전 버전도 보존합니다. 각 본문은 `### GENERATION`과 `### REVISION` 구역으로 나뉩니다. 활성 버전 누락·중복·형식 오류는 명시적으로 실패하며 코드 기본값으로 대체하지 않습니다.

새 환경에서는 기존 DB 백업을 보관한 후 아래 순서로 적용합니다. 모델 호출은 발생하지 않습니다.

```bash
docker compose up -d --no-deps --build backend
docker compose exec -e PYTHONPATH=/srv/growpath backend python tools/install_track_prompts.py
docker compose exec -e PYTHONPATH=/srv/growpath backend python tools/test_track_prompts.py
```

등록 도구는 이전 활성 버전을 비활성화하고 부모 버전에 연결한 새 버전을 트랜잭션으로 활성화합니다. 같은 내용으로 재실행하면 새 버전을 만들지 않습니다. Free Track에는 비용이 0으로 확인된 자료만 전달하고, 유료·비용 미확인 자료를 반환하면 서버에서도 거부합니다. 실제 AI 생성 품질 검증은 별도입니다.

프롬프트를 되돌릴 때는 `prompt_versions`에서 이번 변경의 활성 버전·`parent_version_id`를 확인하고, 해당 agent_id의 현재 버전을 비활성화한 뒤 부모 버전을 한 트랜잭션에서 활성화합니다. **백엔드 코드도 해당 이전 정책을 사용하던 버전으로 함께 되돌립니다.** DB 연결 도입 전 버전은 구역 형식도 달라 호환되지 않습니다. 개인 로드맵 제목 데이터는 이 등록 도구가 변경하지 않습니다.


### Free Track 후속 경계 처리 (#38 / PR #41)

Free Track만 후보 순위·개수 제한·본문 용량 배분 전에 비용 0 자료를 선별합니다. 시연 생성·재생성·수정은 유료·가격 미확인 자료를 제외하고 이유를 남깁니다. 모델 출력의 마지막 무료 검증은 유지합니다.

최초 확정과 수정안 적용은 저장 트랜잭션에서 `app_ext.resource_meta.cost_won`을 직접 조회하고 가격 행을 잠급니다. 유료·NULL·삭제된 자료가 섞이면 `409 FREE_TRACK_PRICE_CHANGED`로 저장을 거부하며 계획을 조용히 바꾸지 않습니다. Fast/Challenge Track의 후보 선정과 가격 처리는 유지합니다. DB 스키마·프롬프트 재설치는 필요하지 않습니다.

회귀 검사는 백엔드 디렉터리에서 `PYTHONPATH=. python -m unittest discover -s tests -p test_free_track_regressions.py -v`로 실행합니다. 실제 모델 호출이나 DB 쓰기를 하지 않고 생성·재생성·수정·확정·수정안 적용과 다른 Track 무영향을 확인합니다.

삭제된 자료는 실제 행 삭제와 content_status=deleted 표시를 모두 확인합니다. Free 활동 저장 시 카탈로그를 갱신하고 검증된 0원을 활동별 비용에도 반영합니다.

예전 Free 계획에 완료한 유료 활동이 남아 있어도 무료 전용 정책의 예외는 없습니다. 수정안 적용은 409로 거부하며 무료 자료로 다시 생성하거나 다른 Track을 선택하라는 메시지를 화면에 전달합니다. 기존 기록이나 활동을 자동 삭제하지 않습니다.

### 스킬별·Track별 강좌 후보 (#47)

로드맵 생성·재생성·수정은 `catalog_candidates.py`와 `catalog_budget.py`를 사용합니다. 전체 강좌에서 스킬별로 최대 20개를 검토합니다. Fast는 앞쪽 핵심 스킬 최대 3개·60개 강좌, Free/Challenge는 최대 5개·100개 강좌입니다. 여러 스킬에 연결된 같은 강좌는 중복 슬롯을 소비하지 않고 다음 후보로 채웁니다. 기존 선택 자료는 별도로 우선 보존하며 도서·공식 문서는 보조 후보 최대 4개입니다. 보조 자료도 동일한 관련성·적합도 순위에 따라 배치하고 앞쪽 고정 슬롯을 주지 않습니다. 실제 AI 전달 상한은 모든 자료를 합쳐 기본 32개입니다. 스킬이 4~5개이거나 필수 선택 자료가 32개를 넘는 경우에만 최대 40개를 시도하며, 후보 부족·입력량 한도에 따라 줄어들 수 있습니다.

Free는 비용이 확인된 0원 자료만 검색합니다. Fast/Challenge는 `관련성 × (1 + 관점 적합도)`로 순위를 정합니다(적합도 0~1). Fast는 목표 관련 단원의 비율·직접 구현과 짧은 시간을 함께 평가합니다. 확보한 유효 단원이 6개 이상이고 목표 관련 단원이 1/3 미만인 일반 강좌는 Fast에서 제외합니다. 단원이 적거나 미확보인 경우 이 비율만으로 제외하지 않고, 사용자가 명시적으로 선택한 자료는 보존합니다. 최대 6주·핵심 스킬 3개는 LLM의 로드맵 편성 지침이며, 기간보다 긴 강좌나 시간 미확인 강좌도 시간만으로 일괄 제외하지 않습니다. 강좌 시간을 변경하거나 생성 결과를 6주 초과로 차단하는 서버 검사는 추가하지 않습니다.

Challenge는 DB 활성 프롬프트에 맞춰 목표 관련 단원의 **설계·성능 측정·문제 해결**을 단순 구현·배포 반복보다 높게 평가합니다. 심화 단원 수(4개에서 상한)와 세 행동의 다양성이 적합도의 55%, 기존 실무 행동 다양성과 단원 수가 각각 10%입니다. 확보된 목차에 목표 관련 심화 단원이 둘 이상이면 중급·고급 난이도에 심화 근거 비례 가점(최대 20%·25%)을 더합니다. Beginner와 난이도 미확인 자료도 같은 심화 근거를 인정합니다. 유효 단원이 6개 이상인데 심화 근거가 둘 미만이면 **난이도 표시와 관계없이** 점수를 0.8배로 낮추며 제외하지는 않습니다. 명시적으로 선택한 자료는 보존합니다. Fast의 집중도 하한은 적용하지 않습니다.

집중도·실무 깊이·발췌 순위는 개별 수업 제목·설명을 기준으로 하며 섹션 제목의 행동을 하위 수업에 반복 인정하지 않습니다. 단원을 확보했으면 소개의 홍보 문구로 실무 깊이를 추가하지 않고, 목차 미확보 시 소개 기반 적합도 기여는 1/4로 낮춥니다. 중복 단원과 수강 만족도·강의 평가, 선수지식 구역은 제외합니다. 문서 10건·질문 20개 같은 수량을 수업 번호와 매칭하지 않으며, 일반적인 구현·모델·점검 단어만으로 무관한 심화 수업에 가점하지 않습니다. 단어 규칙이므로 문맥이나 모든 한국어 조사·동의어를 이해하는 의미 검색은 아닙니다. 일반 후보의 목표 관련성은 양수여야 하며, 중복률을 낮추기 위한 강제 배제·난이도 할당량은 없습니다. 학습자 수준은 임의로 Beginner/Advanced로 변환하지 않고 기존 `known`·`gaps`·`deepCheck`를 LLM에 유지해 최종 선택·편성에 반영합니다. 구판 진단 후보 생성과 시연 고정 응답은 이번 변경 범위에 포함하지 않습니다.

관련성 판단은 제목, 소개(`curriculum.description`/`syllabus_summary`, 관리자 수정값 우선), 단원별 제목·섹션·설명을 사용합니다. 명시된 선수지식·학습대상·강사 소개 구역, 중지 단원과 제목 누락 단원은 학습 근거에서 제외합니다. 태그가 같아도 제목·학습 본문에 목표 관련 검색 근거가 없으면 일반 후보에서 제외하며, 그 대신 무관한 자료로 개수를 채우지 않습니다. 사용자가 명시적으로 고른 자료는 기존 우선 보존 규칙을 따릅니다. 혼합 문장에 숨은 선수지식을 모두 판별하는 의미 분석은 아니므로 실제 추천 품질 검토는 별도로 필요합니다. 정규화된 검색 본문은 기존 카탈로그 스냅샷이 바뀔 때 재구성하며 DB 갱신 후 카탈로그 무효화/기존 120초 TTL을 따릅니다.

각 후보에는 관련 단원 1~2개(각 최대 50자) 또는 소개 원문 발췌(최대 100자)가 들어갑니다. Fast는 관련 구현 단원, Challenge는 관련 구현·검증·개선·운영 단원도 발췌 순위에 반영합니다. 원문 위치는 `curriculum`의 `[0부터 시작하는 단원 위치, 발췌]`로 전달합니다. 전체 목차를 전달한 것으로 취급하지 않습니다. 근거가 없으면 `evidenceStatus=unavailable`로 표시합니다. 반복 메타데이터는 `catalogDefaults`, 스킬명은 `catalogSkillMap`으로 한 번만 보냅니다. 이 입력 형식은 `catalogPolicy`로 설명합니다. Fast/Challenge의 후보 선정 취지는 `trackGuidance.candidatePreference`로 전달하며 활성 DB 시스템 프롬프트를 변경·대체하지 않습니다. Fast의 기간·핵심 스킬 지침도 `trackGuidance`에 전달하고, 모델 입력의 `handoff.prefs.deadlineWeeks`는 사용자 지정 기간과 6주 중 짧은 값으로 전달합니다. 저장된 사용자 설정은 바꾸지 않습니다. 단원 관련성 집계는 자료당 최근 질의 최대 4개를 캐시하고 카탈로그 갱신 시 폐기합니다. DB 테이블과 화면 구성은 바꾸지 않습니다.

실제 진단 전달부 `build_handoff`는 목표·진단 텍스트에서 DB에 등록된 스킬 이름을 최대 5개 추려 `handoff.skillNames`에 기록합니다. 키워드 규칙 기반 연결이며 별도 의미 모델의 판단은 아닙니다. Fast는 그중 앞쪽 최대 3개를 검색하고 LLM에도 같은 핵심 스킬 목록을 보냅니다. 구판 handoff에 이름이 없으면 동일 규칙으로 추정합니다. `trackPolicyVersion`을 캐시 키에 포함해 정책 변경 후 예전 생성 안을 그대로 재사용하지 않습니다. `handoff.selectedResourceIds`, 기존 계획 자료, 사용자가 선택한 자격은 우선 보존합니다. Free에서 유료·가격 미확인 자료는 기존 정책대로 제외하며 `catalogExcluded`에 남깁니다. 삭제/추천 불가인 필수 자료, 필수 자료 40개 초과, 입력량 초과는 명시적으로 실패합니다. 진단의 `resourceHints`는 스킬별 검색 범위 안에서 우선 검토하고 개수 제한을 우회하지 않습니다.

Fast의 핵심 학습 스킬(`handoff.skillNames`·`trackGuidance.coreSkills`)과 과제 분류용 `skillTags`는 구분합니다. 생성·다시 만들기·수정안 모두 DB의 전체 태그 목록을 보존하여 Docker·MLOps 과제를 핵심 3개 중 무관한 태그에 억지로 맞추지 않게 합니다. 실제 과제에서 수행하는 스킬만 1~3개 붙이며, 보조 태그 때문에 별도 학습 스킬·과제를 늘리지는 않도록 입력에 명시합니다. 등록되지 않은 태그 제거와 과제당 3개 제한은 유지합니다. 정책 버전을 올려 이전 제한으로 생성한 후보 캐시를 재사용하지 않습니다. 확정한 로드맵의 기존 태그를 자동 수정하는 작업은 포함하지 않습니다.

입력량은 `Qwen/Qwen3.8-27B` revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`의 공개 토크나이저로 CPU에서 계산합니다. 가중치나 추론 호출은 필요 없습니다. 후보 입력 5,000토큰(확장 시 6,000), 시스템·handoff·기존 계획·수정 요청을 합친 입력 10,000토큰을 상한으로 두며 채팅 포장 여유 128토큰을 더합니다. 설정된 Ollama 문맥이 16,384보다 작으면 출력 4,096과 여유 2,048을 먼저 빼고 상한을 줄입니다. 이는 배포된 Ollama 템플릿·생각 길이 전체의 보증이나 OpenAI의 정확한 과금 토큰 수가 아닙니다. 입력 본문/필수 자료를 조용히 자르지 않으며 여유가 없으면 후보를 줄이거나 안내 오류를 반환합니다.

Docker는 백엔드 재빌드 시 공개 토크나이저 약 13MB를 고정 URL에서 받아 SHA-256 `0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3`을 확인합니다. 요청 중 다운로드하지 않으며 파일 누락·해시 불일치는 명시적 오류입니다. 호스트 실행은 `requirements.txt` 설치 후 backend에서 `python tools/install_catalog_tokenizer.py`를 한 번 실행합니다. 경로를 바꿀 때만 `ROADMAP_TOKENIZER_PATH`를 설정합니다. 외부 파일은 Git에서 제외합니다.

검사 명령(backend 기준):

```bash
python -m unittest discover -s tests
PYTHONPATH=. python tools/test_track_prompts.py
python tools/verify_course_candidates.py --output /tmp/course-candidates-verification.json
```

마지막 명령은 실제 앱 DB를 읽기 전용 트랜잭션으로 조회합니다. 6개 목표×3안의 후보 수·무료 조건·선택 보존·원문 발췌·입력 한도와 처리 시간을 검사하고 모델은 호출하지 않습니다. 시스템 지시문은 실제 DB 활성 버전을 사용하며 코드로 대체하지 않습니다. 단위 검사는 별도로 경계/실패/생성/수정 경로를 확인합니다. 실제 모델 품질·응답 지연·동시 부하는 별도 검증 대상입니다.

이번 변경은 **DB 프롬프트를 수정하거나 재등록하지 않습니다.** Free/Fast/Challenge 생성·수정 지시문은 기존 `public.prompt_versions`의 활성 버전을 그대로 읽습니다. Fast 6주·핵심 스킬 3개는 시스템 프롬프트 수정 대신 생성 입력의 추가 조건으로 전달합니다. Challenge의 실무 적용 비중은 DB 지시문과 LLM의 최종 편성에 맡기고, 서버에서는 관련 실습 근거가 있는 강좌 후보를 지원합니다.

적용은 최신 백엔드 이미지를 빌드·교체하며 DB 테이블 마이그레이션이나 프롬프트 등록 명령을 실행하지 않습니다. 되돌리기는 이전 백엔드 이미지로 교체합니다. 이미 확정한 계획의 내용·시간·조회에는 새 제한을 적용하지 않습니다.

### 로드맵 생성 시간 초과 조정 (#47)

`OPENAI_ROADMAP_TIMEOUT`은 OpenAI 로드맵 생성·재생성·수정 요청의 HTTP 대기 제한입니다. 기본 180초, 설정 범위 1~600초이며 잘못된 값은 시작 시 오류로 알립니다. 다른 OpenAI 기능은 기존 90초, 연결 확인은 15초, Ollama는 기존 `OLLAMA_TIMEOUT`을 사용합니다. 설정 변경 후 백엔드를 재시작하며 90으로 설정하면 이전 제한으로 돌아갑니다. HTTP 대기 제한은 전체 작업의 정확한 종료 시각이나 외부 프록시 제한을 보장하지 않습니다.

강좌 후보는 기본 32개·최대 40개와 기존 근거·입력 한도를 유지합니다. 사용자 추론 정도를 자동으로 낮추지 않습니다. 기존 AI 모델 설정에서 고른 값이 우선하며, 없으면 `OPENAI_REASONING_EFFORT`, 그것도 없으면 모델 기본값을 따릅니다. `low` 비교는 동일 목표·후보·DB 프롬프트에서 별도로 검증하고 품질과 소요 시간을 함께 기록합니다. 이 설정은 대기 중 실패를 줄이기 위한 것으로 생성 속도 개선을 보장하지 않습니다.

실패한 안만 사용자가 재시도하는 기존 동작과 성공한 안의 보존을 유지합니다. 자동 유료 재호출은 추가하지 않습니다. PR #46의 무료 필터·저장 직전 가격 검사는 A1에만 적용되며, Fast(A2) 생성의 추가 LLM 호출이나 가격 잠금은 없습니다. Fast의 6주·핵심 3스킬 조건이 모델 편성에 주는 영향은 같은 후보 목록을 고정한 별도 비교 대상으로 둡니다. 비교를 위해 DB 프롬프트나 실제 사용자 설정을 바꾸지 않습니다.

무료 검사: backend에서 `python -m unittest discover -s tests -p test_reasoning.py -v`로 역할별 제한·사용자 추론값 유지·설정 경계·시간 초과 시 1회만 호출함을 확인합니다. 전체 회귀 검사는 위의 `python -m unittest discover -s tests`를 사용합니다. 실제 유료 호출은 별도 합의된 범위에서만 실행합니다.
