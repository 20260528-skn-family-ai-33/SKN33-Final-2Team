# API 계약 (화면이 백엔드에 기대하는 것)

화면(`frontend/`)이 실제로 부르는 API와 그 약속이에요. 기준은 **`frontend/src/api/`의 코드**이고, 이 문서는 그 요약이에요. 계약을 바꾸면 `api/endpoints/*`·`api/types/*`와 이 문서를 함께 고쳐요.

- 응답 모양은 참고용 백엔드(`backend/` = 5차 FastAPI)에서 확인했어요.
- 설계서 v1.7 원문과의 한 줄씩 대조는 이번 작업에서 하지 않았어요(needs_review). 아래 "설계서 밖" 표시는 백엔드 코드 주석에 그렇게 적힌 것만이에요.

## 공통 약속

| 항목 | 약속 | 화면 코드 |
| --- | --- | --- |
| 주소 | 모두 `/api/v1/...`. 화면과 같은 출처(개발: Vite 프록시, 배포: nginx·CloudFront 경로 분기) | `api/client.ts` `API_BASE` |
| 로그인 | 서버가 HttpOnly 세션 쿠키(SameSite=Lax)를 준다. 화면은 쿠키만 보내고 토큰을 다루지 않음 | `credentials: 'same-origin'` |
| 오류 | 2xx 가 아니면 본문 `{"error": {code, message, hint, retryable, kind, cause, raw}}`. `message`는 사용자 문구, `cause`·`hint`·`raw`는 "자세히 보기(운영자용)" | `ApiError`, `shared/state/ai.ts` `cause()` |
| 오래 걸리는 작업 | 요청 머리에 `Prefer: respond-async`를 붙이면 `202 {jobId, status:'running'}`. 화면은 `GET /jobs/{id}?wait=10`(서버가 최대 10초 붙잡음)을 끝날 때까지 되풀이. 멈추기는 `POST /jobs/{id}/cancel` | `api/jobs.ts` |
| 작업 결과 | `{jobId, kind, status: running·done·failed·cancelled, progress, result, error}`. 실패 원인은 `error`(위 오류와 같은 칸) | `JobView` |
| 문서에 진행을 적는 작업 | 3안 작성·다시 만들기·지원 조건 확인처럼 서버가 진행 상태를 작성 문서(로드맵 기록)에 적는 일은 202 대신 문서를 바로 돌려주고, 화면이 문서를 다시 읽어 진행을 봄 | `useDraftWatch`·`usePlanWatch` |
| 규정·자료 묶음 | 규정 조항·학습 자료가 나오는 응답에는 화면이 그릴 조항·자료를 `reg`·`res` 묶음으로 함께 보냄(화면이 따로 조회하지 않게) | `mergeReg`·`mergeRes` |
| 작성 문서 자동 저장 | 화면이 고칠 때마다 400ms 뒤 `PATCH /drafts/{id}`로 바뀐 칸만 보냄. `genCur`(3안별 보고 있는 버전)는 바뀐 때만 보냄 | `features/draft/draftSync.ts` |

## 엔드포인트 (영역별)

`{}`는 경로 값. 화면 함수 이름은 `api/endpoints/<파일>`의 이름이에요.

### 계정·내 정보·AI 모드·시연 도구 — `account.ts` (`accountApi`·`aiApi`·`demoApi`)

| 요청 | 쓰는 곳 |
| --- | --- |
| `POST /auth/login` · `POST /auth/logout` · `GET /me` | 로그인·로그아웃·새로 고침 때 계정 |
| `GET /me/workspace` | 로그인 뒤 내 기록 전체(작성 문서·로드맵·보고서) |
| `GET /me/profile` · `PUT`/`DELETE /me/profile/self` · `PUT /me/evaluations/{period}/consent` | 내 정보(동의는 `{period, consent}`를 돌려줌) |
| `GET /me/goal-suggestions` · `POST /me/goal-suggestions/regenerate` | 작성 1단계 목표 후보 |
| `GET /ai/providers` · `PUT /me/ai-provider` · `GET /ai/status?provider=` · `GET /ai/log` | 좌측 AI 모델 고르기·연결 상태·에이전트 동작 보기(시연·디버그 전용 · 직원·관리자 계정 모두 · 누가 호출했든 모든 계정의 최근 호출을 `employee`(누구의 일)·`by`(관리자 화면에서 시작하면 '관리자')와 함께 줌 · 운영에서는 끔) |
| `GET /demo/accounts` · `PUT /me/demo-settings` · `POST /demo/reset` · `POST /demo/jump` | 시연 전용(로그인 직원 고르기·가데이터·실패 시연·단계 이동·초기화) |

`GET /ai/providers`의 `providers[].models`는 `{default, roadmap, regulation, embed, vision}`이에요. `default`는 진단 에이전트, `roadmap`은 로드맵 에이전트, `regulation`은 규정 에이전트(사내 생활 도우미 답변·안별 지원 조건 확인), `vision`은 기획서 이미지 읽기 모델이에요. `regulation`이 없는 옛 응답이면 화면은 `default`를 써요. `GET /ai/status?provider=ollama`의 `models[]`는 `{role, name, installed, loaded}`이고, `default` 다음에는 `default`와 이름이 다른 `roadmap`·`regulation`만 들어가요(같은 이름이면 Ollama에 한 번만 올라가서) (#33).

평정 동의 요청은 `{ "consent": true }` 또는 `{ "consent": false }`만 받는다. 누락·NULL·문자열·숫자는 `422 / CONSENT_REQUIRED`이며 기존 동의값을 보존한다. 개인 입력의 `devYears`가 숫자로 바뀌지 않거나 0~50년 범위를 벗어나면 `422 / DEV_YEARS_RANGE`를 반환하고 기존 입력을 보존한다. #15의 격리 DB·실제 인증 API 검사로 확인했다.

### 새 로드맵 작성 — `drafts.ts`

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /drafts/current` · `POST /drafts` · `PATCH /drafts/{id}` · `DELETE /drafts/{id}` | 작성 문서 읽기·만들기·자동 저장·버리기 |
| `POST /drafts/{id}/changes/apply` · `.../changes/revert` (본문 `{kind}`) | 앞 단계를 바꿨을 때 뒤 단계 결과 버리기·되돌리기 |
| `POST`/`DELETE /drafts/{id}/project-file` · `POST .../project-file/summary` | 기획서 올리기·지우기·요약(작업) |
| `POST /drafts/{id}/assessment` · `POST .../diagnosis` · `PUT .../diagnosis/overrides` | 사전 점검 문항(작업) · 진단(작업) · 점검 결과 수정 |
| `POST /drafts/{id}/options` · `GET .../options` · `POST .../options/{pid}/retry` · `.../options/accept-partial` | 3안 작성 시작(문서에 진행을 적음)·다시 읽기·실패한 안 다시·일부만 받기 |
| `POST /drafts/{id}/options/{pid}/regenerate` | 한 안 다시 만들기. 본문 `{request: {wish, quick[], removeActs[{key,title}], replaceActs[{key,title}]} \| null}` |
| `POST /drafts/{id}/options/support/retry` | 지원 조건 다시 확인. 본문 `{perspective: 안 ID \| null(세 안 모두)}` |
| `POST /drafts/{id}/selection` · `POST /drafts/{id}/confirm` | 안 고르기 · 확정(→ `{planId}`) |

### 확정 로드맵·점검·보고서 — `plans.ts`

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /plans/{id}` · `PUT /plans/{id}/activities/{act}/progress` | 로드맵 읽기 · 활동 기록(완료·메모) |
| `POST /plans/{id}/activities/{act}/attachments` | 결과물·수료증 첨부(사후 점검 파일도 `act='post'`로 같은 곳) · 본인의 진행 중 로드맵과 그 로드맵의 활동만(아니면 404·409) |
| `POST /plans/{id}/archive` · `.../resume` | 보관·다시 진행 |
| `POST /plans/{id}/revisions` · `.../revisions/support/retry` · `POST /revisions/{rid}/accept` · `DELETE /revisions/{rid}` | 수정 요청(작업) · 지원 조건 다시 · 수정안 확정 · 버리기 |
| `POST /plans/{id}/comments/{cid}/read` | 부서장 코멘트 읽음 |
| `PUT /plans/{id}/post-assessment` · `POST .../post-assessment/deep` | 사후 점검 저장 · 심화 질문 사후 문제(작업 · 설계서 밖 추가 10/23) |
| `POST /plans/{id}/reports` · `GET /reports?planId=` · `POST /reports/{rid}/confirm` | 보고서 만들기(작업) · 목록 · 확인 |

### 학습 자료·자격증·규정·스킬 지도 — `catalog.ts`

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /certifications` | 자격증 2단계 고르기 |
| `GET /resources?kind=&q=&limit=&offset=` · `POST /resources/lookup` · `GET /resources/{id}` | 학습 자료 목록(30개씩)·여러 개 조회 |
| `GET /regulations/sets` · `POST /regulations/lookup` | 직원 구분별 규정 묶음 · 조항 조회 |
| `GET /skills/map` | 스킬 지도(설계서 밖 추가 · 10/23) |

### 사내 생활 도우미 — `assistant.ts`

| 요청 | 쓰는 곳 |
| --- | --- |
| `POST /assistant/ask` (작업) | 본문 `{question, history: [{q, a: 답 요약}]}` → 결과 `{answer, reg, meta}`. `answer.kind`: regulation(근거 조항 `basis`) · general(사내 홈페이지 안내 `intranet` / 업무·학습 / 앱 사용법 `links`) · clarify(되묻기 `options`) · out(범위 밖) |

### 부서장 — `team.ts`

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /team/members` · `GET /team/members/{uid}/plans` | 소속 직원 목록 · 직원 기록(공개 범위만). 직원 정보는 이름·사번·소속·직급·직위·부서장 여부만(`TeamUser`), 보고서에서는 심화 질문 결과·목표 달성 답·결과물 첨부를 뺌 |
| `POST /team/plans/{pid}/comments` · `PATCH /team/plans/{pid}/comments/{cid}` | 코멘트 보내기 · 고치기(설계서 밖 추가 · 10/23) |

### 관리자 — `admin.ts` (5차 목업에서 추가 · 2026-10-21 사용자 결정 · 설계서 반영 여부는 사람 확인 필요)

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /admin/overview` | 개요 |
| `GET /admin/datasets/{ds}/rows?sheet=&q=&limit=&offset=` | 데이터 표(`ds`: hr·education · 규정은 표로 다루지 않음) |
| `POST /admin/datasets/{ds}/edit` | 한 건 고치기. 본문 `{rows}`면 확인만(바뀌는 칸·오류·`token`), `{rows, save:true, token, goalMode}`면 저장 |
| `GET /admin/datasets/{ds}/export?format=&sheet=` · `.../template?...` | 엑셀·CSV 내려받기(링크로 염) |
| `POST /admin/datasets/{ds}/preview`(파일) · `GET /admin/uploads/{id}` · `POST .../apply` · `DELETE /admin/uploads/{id}` · `GET /admin/uploads?dataset=` | 파일 미리보기 · 다시 보기 · 반영 · 취소 · 이력 |
| `GET /admin/goal-suggestions/employees` | 목표 후보를 다시 만들 직원 고르기(재직 직원 · 지금 후보 상태와 만든 모드) |
| `POST /admin/goal-suggestions/regenerate-all` | 목표 후보 다시 만들기. 본문 `{ mode, employeeIds? }` — `mode`: `mock`(가데이터) · `ollama` · `openai`(관리자가 고른 모델 · 직원 설정은 그대로) · `null`(각 직원이 고른 AI 모드). `employeeIds`가 있으면 그 직원만(재직 직원만 받음 · 없으면 400 `NO_EMPLOYEES`). 고른 모델을 지금 쓸 수 없으면 409 `AI_UNAVAILABLE` |
| `GET /admin/regulations` | 규정 데이터 '지금 규정': 도우미가 쓰는 버전의 규정 목록(`id`·`name`·`group`·`version`·`effective`·`fileName`·`size`·`available`). 규정이 많은 직원 구분부터 |
| `GET /admin/regulations/{id}/pdf` | 지금 규정 원문 PDF 내려받기(링크로 염 · 서버에 원문이 없으면 404 `NO_PDF`) |
| `POST /admin/regulations/uploads`(파일 `file` + `memo`) · `GET /admin/regulations/uploads` | 새 규정 PDF 올리기(PDF만 · 20MB · 메모 500자 · 201) · 올린 PDF 목록(처리 상태 없음) |
| `GET /admin/regulations/uploads/{id}/pdf` | 올린 PDF 내려받기 |
| `DELETE /admin/regulations/uploads/{id}` | 잘못 올린 PDF 지우기(서버 파일과 기록을 함께 · 되돌릴 수 없음 · 204, 없으면 404 `NO_UPLOAD`) |

규정은 관리자가 고치지 않아요(2026-10-26 사용자 결정): 규정은 벡터 DB를 거친 RAG에 쓰여서, 관리자가 올린 PDF는 시스템 관리자(서비스 운영팀)가 내려받아 임베딩·벡터 DB를 갱신해요. 그래서 예전의 규정·조항 엑셀/한 건 고치기(`/admin/datasets/regulations/*`)와 규정 색인 만들기(`POST /admin/regulations/index`)는 없앴어요. 개요(`GET /admin/overview`)의 `regulations` 는 `{count, files, uploads, lastUpload}` 이고, 모델 설정 여부는 맨 위 `providers` 에 있어요.

## 타입 위치

| 내용 | 파일 |
| --- | --- |
| 오류 본문·작업·공통 | `api/types/common.ts` |
| 계정·내 정보·목표 후보·시연 계정 | `api/types/account.ts` |
| 작성 문서(세부 사항·문항·진단·3안·다시 만들기 요청·점검 결과 수정) | `api/types/draft.ts` |
| 확정 로드맵·진행·수정안·코멘트·사후 점검·보고서 | `api/types/plan.ts` |
| 학습 자료·자격증·규정·스킬 지도 | `api/types/catalog.ts` |
| 부서장 | `api/types/team.ts` |
| 관리자 | `api/types/admin.ts` |
| 도우미 답 | `api/endpoints/assistant.ts` |

에이전트(모델) 출력이 그대로 들어오는 칸은 필요한 칸만 타입으로 적고 나머지는 `[k: string]: unknown`으로 열어 뒀어요(모델 출력은 칸이 늘 수 있어서).

## 5차 화면 ID가 남아 있는 곳

서버가 5차 해시 주소의 화면 ID를 값으로 돌려주는 곳이 있어 화면이 새 주소로 바꿔 써요(`app/paths.ts`).

| 어디 | 값 예시 | 화면 처리 |
| --- | --- | --- |
| 작업 공간 `lastNew`(마지막 작성 단계) | `new-details`, `new-options` | `newIdToPath` · 저장할 때는 `pathToNewId`로 되돌려 같은 값을 보냄 |
| `POST /demo/jump` 결과 `entry` | `home`, `new-quiz`, `post:{planId}`, `report:{rid}` | `legacyToPath` |
| 도우미 답 `answer.links` | `[['roadmap','내 로드맵'], ['checks','점검·보고서']]` | `legacyToPath` |

새 백엔드에서는 이 값을 "화면 키"로 계속 쓸지, 경로 문자열로 바꿀지 정해 주세요. 어느 쪽이든 화면은 `paths.ts` 한 곳만 고치면 돼요.
