# API 계약 (화면이 백엔드에 기대하는 것)

화면(`frontend/`)이 실제로 부르는 API와 그 약속이에요. 기준은 **`frontend/src/api/`의 코드**이고, 이 문서는 그 요약이에요. 계약을 바꾸면 `api/endpoints/*`·`api/types/*`와 이 문서를 함께 고쳐요.

- 응답 모양은 참고용 백엔드(`backend/` = 5차 FastAPI)에서 확인했어요.
- 설계서 v1.7 원문과의 한 줄씩 대조는 이번 작업에서 하지 않았어요(needs_review). 아래 "설계서 밖" 표시는 백엔드 코드 주석에 그렇게 적힌 것만이에요.

## 공통 약속

| 항목 | 약속 | 화면 코드 |
| --- | --- | --- |
| 주소 | 모두 `/api/v1/...`. 화면과 같은 출처(개발: Vite 프록시, 배포: nginx·CloudFront 경로 분기) | `api/client.ts` `API_BASE` |
| 로그인 | 챗봇을 포함한 회원 API는 HttpOnly 세션 쿠키를 사용 | `credentials: 'same-origin'` |
| 오류 | 2xx 가 아니면 본문 `{"error": {code, message, hint, retryable, kind, cause, raw}}`. `message`는 사용자 문구, `cause`·`hint`·`raw`는 "자세히 보기(운영자용)" | `ApiError`, `shared/state/ai.ts` `cause()` |
| 오래 걸리는 작업 | 요청 머리에 `Prefer: respond-async`를 붙이면 `202 {jobId, status:'running'}`. 화면은 `GET /jobs/{id}?wait=10`(서버가 최대 10초 붙잡음)을 끝날 때까지 되풀이. 멈추기는 `POST /jobs/{id}/cancel` | `api/jobs.ts` |
| 작업 결과 | `{jobId, kind, status: running·done·failed·cancelled, progress, result, error}`. 실패 원인은 `error`(위 오류와 같은 칸) | `JobView` |
| 문서에 진행을 적는 작업 | 3안 작성·다시 만들기·지원 조건 확인처럼 서버가 진행 상태를 작성 문서(로드맵 기록)에 적는 일은 202 대신 문서를 바로 돌려주고, 화면이 문서를 다시 읽어 진행을 봄 | `useDraftWatch`·`usePlanWatch` |
| 규정·자료 묶음 | 규정 조항·학습 자료가 나오는 응답에는 화면이 그릴 조항·자료를 `reg`·`res` 묶음으로 함께 보냄(화면이 따로 조회하지 않게) | `mergeReg`·`mergeRes` |
| 작성 문서 자동 저장 | 화면이 고칠 때마다 400ms 뒤 `PATCH /drafts/{id}`로 바뀐 칸만 보냄. `genCur`(3안별 보고 있는 버전)는 바뀐 때만 보냄 | `features/draft/draftSync.ts` |

## 엔드포인트 (영역별)

### 자료 선택 기간 — `/api/v2/drafts/{id}/recommendations/durations`

기간 응답의 `durationEstimates[skill]`은 `resource-hours-books/v3` 기준이다. `startWeek`·`endWeek`·`weeks`는 해당 스킬 자료의 달력 구간이며, 공유 강좌·도서 때문에 다른 스킬과 겹칠 수 있다. 화면 합계는 `weeks`를 더하지 않고 `totalWeeks`를 사용한다. `addedWeeks`는 해당 스킬이 전체 일정에 더한 주차이고, 자료가 없는 스킬은 0주와 null 구간으로 표시한다.

같은 강좌 ID는 전체에서 한 번만 시간에 포함한다. 도서는 고유 ID당 1주이며, 여러 스킬에서 같은 책을 선택하면 첫 배정 구간을 공유한다. `bookWeeks`는 해당 스킬에서 새로 추가한 도서 주차이므로 이미 배정된 책은 0이다. 제목이 같아도 ID가 다르면 별도 도서로 센다. 미확인 강좌 시간의 1주 가정과 숫자로 확보한 추정 시간은 구분한다. `scheduleKey`·`selection`·`skillOrder`·`weeklyHours`로 현재 선택과 계산 결과의 일치를 확인한다. 선택·순서·주당시간이 바뀌면 전체를 다시 계산하고 오래된 결과의 저장을 거부한다. v2 캐시도 다시 계산해야 하므로 백엔드·프런트를 함께 배포한다.

새 계획에는 공유 강좌·도서의 `resourceWindow: {from,to}`, `durationBasis: materials-only`, `totalHUnknown`·`totalHEstimated`가 포함될 수 있다. `totalH`도 같은 강좌·도서 ID는 한 번만 더하지만 활동 ID·소속 스킬은 유지한다. 자료 기간에는 과제 소요 주차가 포함되지 않으며 과제 시간은 `totalH`에 남는다. 기존 확정 계획은 일괄 변경하지 않으며 도서 완료 상태를 함께 갱신하는 변경도 포함하지 않는다.

추천 스킬 응답에는 선택적인 `courseDiagnostic: {reason,detail}`이 올 수 있다. 후보 없음, 근거·기술·범위 부족 또는 긴 강좌가 필요한 사유를 기록하며, 일부 강좌를 추천한 경우에도 남은 범위의 부족을 설명할 수 있다. 기존 진단 필드 없는 응답도 허용한다. 이 필드는 현재 추천 화면에 별도 표시하지 않는다.

`{}`는 경로 값. 화면 함수 이름은 `api/endpoints/<파일>`의 이름이에요.

### 계정·내 정보·AI 모드·시연 도구 — `account.ts` (`accountApi`·`aiApi`·`demoApi`)

| 요청 | 쓰는 곳 |
| --- | --- |
| `POST /auth/login` · `POST /auth/logout` · `GET /me` | 로그인·로그아웃·새로 고침 때 계정 |
| `GET /me/workspace` | 로그인 뒤 내 기록 전체(작성 문서·로드맵·보고서) |
| `GET /me/profile` · `PUT`/`DELETE /me/profile/self` · `PUT /me/evaluations/{period}/consent` | 내 정보(동의는 `{period, consent}`를 돌려줌) |
| `GET /me/goal-suggestions` · `POST /me/goal-suggestions/ensure` · `POST /me/goal-suggestions/regenerate` | 저장된 후보 조회 · 누락/변경 확인 · 명시적 다시 만들기 |
| `GET /ai/providers` · `PUT /me/ai-provider` · `GET /ai/status?provider=` · `GET /ai/log` | 좌측 AI 모델 고르기·연결 상태·에이전트 동작 보기(시연·디버그 전용 · 직원·관리자 계정 모두 · 누가 호출했든 모든 계정의 최근 호출을 `employee`(누구의 일)·`by`(관리자 화면에서 시작하면 '관리자')와 함께 줌 · 운영에서는 끔) |
| `PUT /me/reasoning` | 좌측 AI 모델에서 모델별 추론 정도 고르기(직원 계정만) |
| `GET /demo/accounts` · `PUT /me/demo-settings` · `POST /demo/reset` · `POST /demo/jump` | 시연 전용(로그인 직원 고르기·가데이터·실패 시연·단계 이동·초기화) |

`GET /ai/providers`의 `providers[].models`는 `{default, roadmap, regulation, embed, vision}`이에요. `default`는 진단 에이전트, `roadmap`은 로드맵 에이전트, `regulation`은 규정 에이전트(사내 생활 도우미 답변·안별 지원 조건 확인), `vision`은 기획서 이미지 읽기 모델이에요. `regulation`이 없는 옛 응답이면 화면은 `default`를 써요. `GET /ai/status?provider=ollama`의 `models[]`는 `{role, name, installed, loaded, think}`이고(`think`는 아래 추론 정도 · 진단·로드맵 모델만), `default` 다음에는 `default`와 이름이 다른 `roadmap`·`regulation`만 들어가요(같은 이름이면 Ollama에 한 번만 올라가서) (#33).

추론 정도 요청은 `{ "provider": "ollama" | "openai", "level": "<단계 이름>" | null }`이고 그 모드의 값만 바꿔(다른 모드 값은 그대로 · 동시에 저장해도 사라지지 않음) 모드별로 저장한 전체 `{reasoning: {ollama?, openai?}}`를 돌려준다. 화면은 저장을 하나씩 차례로 보내고 마지막 선택의 응답만 화면에 맞춘다. `null`은 그 모드를 서버 기본값으로 되돌린다. 단계 이름은 소문자·숫자·`_`·`-` 20자 이내만 받고 `true`·`false` 같은 값은 받지 않는다(`422 / BAD_REASONING`). OpenAI는 서버의 단계 목록 밖이면 같은 오류다. 고를 수 있는 단계는 이렇게 온다.

- OpenAI: `GET /ai/providers`의 openai 항목 `reasoning: {levels, default, modelDefault}`. `levels`는 `.env`의 `OPENAI_REASONING_LEVELS`이고 비면 기본 모델 gpt-6-luna의 코드 값(`none`~`xhigh`)이다(다른 모델이면 빈 목록 = 고르지 못함). `default`는 `.env`의 `OPENAI_REASONING_EFFORT`(비면 `null` = 보내지 않음), `modelDefault`는 보내지 않을 때 모델이 쓰는 값(gpt-6-luna `medium` · 모르는 모델이면 `null`)이고 화면 '기본값 · 보통' 표시에만 쓴다.
- RunPod-Ollama: 진단·로드맵 모델에만 고르고, 모델마다 달라 `GET /ai/providers`의 `reasoning.levels`는 `null`이다(`default`는 `.env` 기본값). `GET /ai/status?provider=ollama`에서 진단·로드맵 모델(`role: default`)의 `models[].think: {levels, default}`(Ollama `/api/show` `thinking.values` · 켜고 끄기는 `off`·`on`)로 온다. 확인하지 못하면 `null`, 고를 단계가 없으면 빈 목록이다. 규정 모델 줄의 `think`는 늘 `null`이다.

직원이 고른 값은 `GET /me`·`PUT /me/demo-settings` 응답의 `reasoning`으로 온다. 서버는 고른 값 → `.env` 기본값 순으로(고른 값이 지금 모델이 받는 단계가 아니면 — 모델을 바꾼 뒤 남은 옛 선택 등 — `.env` 기본값 · 단계를 확인하지 못하면 고른 값 그대로) Ollama에는 `think`(on/off는 true/false, 나머지는 단계 이름), OpenAI에는 `reasoning_effort`로 보내고, 둘 다 없으면 보내지 않아 모델 기본값을 따른다. **RunPod-Ollama 규정 에이전트(사내 생활 도우미·안별 지원 조건 확인) 호출은 생각을 끄고 학습한 모델이라 고른 값·`.env`와 관계없이 늘 `think: false`다.** 이미지 읽기 모델에는 직원 값을 쓰지 않는다. 관리자가 모델을 골라 목표 후보를 다시 만들 때는 직원 값 대신 `.env` 기본값을 쓴다.

평정 동의 요청은 `{ "consent": true }` 또는 `{ "consent": false }`만 받는다. 누락·NULL·문자열·숫자는 `422 / CONSENT_REQUIRED`이며 기존 동의값을 보존한다. 개인 입력의 `devYears`가 숫자로 바뀌지 않거나 0~50년 범위를 벗어나면 `422 / DEV_YEARS_RANGE`를 반환하고 기존 입력을 보존한다. #15의 격리 DB·실제 인증 API 검사로 확인했다.

업무 설명(`view.profile.workDesc`·`self.profile.workDesc`)은 `employees.planned_project_description`에서 읽고 같은 열에 저장한다. 빈 값은 NULL이며 최대 500자(`422 / WORK_DESC_LENGTH`)다. 프로젝트는 기존 `employee_input_profiles.project_experience`의 줄바꿈 목록을 사용한다. 둘 다 선택이므로 프로젝트만 입력해도 저장·맞춤 추천이 가능하다. 새 테이블/열은 추가하지 않는다. 새 저장은 `edited.workDesc`를 만들지 않고 처음 값과 변경 해시만 보존한다.

무변경 저장은 원래 입력 프로필 행과 갱신 시점을 보존한다. 업무 설명만 고쳐도 빈 입력 프로필을 만들지 않는다. 되돌리기는 본인이 고친 설명을 처음 값으로 복원하되 기술만 고쳤거나 이후 관리자가 갱신한 설명은 덮지 않는다. 구판 `edited.workDesc`는 명시적 저장/이관 전까지 읽기 호환을 유지한다. 선택 이관 SQL `backend/db/migrate_self_work_descriptions.sql`은 팀 열과 충돌하면 전체 롤백하며 구판 사본에 없던 처음 설명을 추정하지 않는다. 부서장 응답에는 본인 입력을 보내지 않는다.

`POST /auth/login`과 `GET /me`는 목표 생성 요청이나 추천 입력 해시 검사를 하지 않는다. 본인 입력 저장/되돌리기·평정 동의·관리자 수정/업로드의 **저장 성공 뒤 추천 입력 해시가 바뀐 직원만** 백그라운드로 갱신한다. 부서명·상위 부서 변경은 해당/직속 하위 부서의 직원, 보유 자격명 변경은 연결된 직원도 포함한다. 무변경 저장과 저장 실패는 재생성하지 않는다. 목표 화면의 `ensure`는 생성 기록·후보가 모두 없는 계정만 처음 준비하며 기존 후보·실패 상태·설정용 mock 후보를 자동 재생성하지 않는다. 생성 중 정보가 바뀌면 옛 결과는 저장하지 않고 지정 모델로 최신 입력을 준비한다. 실패하면 기존 후보를 보존하고 수동으로 재시도한다. `regenerate`는 명시적 다시 만들기이며 SQL 직접 수정 후에도 사용한다. 배포 전에 사전 생성 도구로 준비할 수 있다.

목표 추천은 본인 입력의 프로젝트를 사용하며, 진단 문항·진단 결과와 로드맵 전달에는 `profile.projectExperience`(최대 5개·각 300자)를 포함한다. 이는 경험 참고이며 업로드한 현재 기획서의 `projectSummary`나 숙련도 증빙으로 대체하지 않는다. 로드맵 전달 내용 화면에도 업무 설명과 프로젝트 경험을 표시한다.

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

`GET /resources`·`POST /resources/lookup`·작업 공간의 자료 첨부는 요약(`detailsLoaded=false`)이다. `content`는 최대 400자, `curriculum`에는 개수(`item_count`)·확보 상태(`coverage`)만 보내고 `items`는 제외한다. `GET /resources/{id}`는 상세(`detailsLoaded=true`)로 전체 소개와 순서 있는 `curriculum.items`(`title`, `section`, `description`)를 제공한다. 목차 유무·자료 유형과 관계없이 요약에 ‘전체 소개·상세 보기’ 링크를 제공한다. 상세 화면은 전체 상세 캐시가 있어도 재진입마다 단건 상세를 조회하며 이후 요약 수신으로 전체 목차를 지우지 않는다.

`curriculum.coverage`는 `public_outline`·`partial_outline`·`sample`·`description_only`이며 목차를 확보하지 못한 것을 빈 강좌로 해석하지 않는다. 원문 강의 전체나 자막을 저장했다는 뜻은 아니다.

`hours`는 일정 계산용 정밀 값이고 `timeStatus`는 `confirmed`·`estimated`·`manual`이다. `durationKind`로 영상/학습 시간을 구분하고 `timeNote`에 출처·추정 근거를 제공한다. 자료·단계·선택지·간트·실행 기록·수정 화면은 공통 함수를 통해 10분 단위로 반올림한다(예: `5.83333` → ‘5시간 50분’). 새 `roadmap_steps.estimated_duration` 문구도 같은 규칙이며 숫자와 일정 계산 정밀도는 유지한다. 관리자 입력에서 시간 숫자는 그대로 두고 시간 추정 표시만 해제해도 `manual`로 저장하고 자동 동기화에서 보존한다. 새 로드맵 활동은 `hoursEstimated`, `hoursBasis`를 함께 저장하며 기존 확정 활동의 시간을 일괄 변경하지 않는다. 과거 활동의 `hoursEstimated`가 없으면 ‘추정 여부 미기록’으로 표시한다. 현재 강좌 시간이 확인돼 있어도 과거 계획 시간을 확인 시간으로 재해석하지 않는다. 025·026 DB 적용과 적재 후 앱을 배포해야 한다.

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /certifications` | 자격증 2단계 고르기 |
| `GET /resources?kind=&q=&limit=&offset=` · `POST /resources/lookup` · `GET /resources/{id}` | 학습 자료 목록(30개씩)·여러 개 조회 |
| `GET /regulations/sets` · `POST /regulations/lookup` | 직원 구분별 규정 묶음 · 조항 조회 |
| `GET /skills/map` | 스킬 지도(설계서 밖 추가 · 10/23) |

### 사내 생활 도우미 — `assistant.ts`

챗봇은 로그인한 직원의 계정별 AI 설정을 따릅니다. 직원 ID는 작업 소유권과 호출 기록에 사용합니다. 모델에는 빈 사용자 상황을 전달하고, 규정 원문의 적용 대상과 질문·앞 대화에 적힌 조건을 사용합니다. 브라우저 대화는 직원별로 분리합니다.

수자원공사 정보로 분류되면 `knowledge.documents`·`knowledge.chunks`의 같은 범주·실제 자료만 벡터 검색해 답변 모델에 전달해요. 회사 답변은 `kind=general`, `source=work`이고 `summary`에 출처가 덧붙어요. 선택 필드 `answer.knowledgeSources[]`는 `{chunkId, documentId, documentTitle, sourceUrl, location, asOf, sourceLimits, isVirtual, textSha256, sourceFileSha256, textTruncated}`이며, 실제 인용한 검색 결과만 들어가요. `basis`는 규정 조항 전용으로 유지해요. 회사 자료에 맞는 근거가 없으면 `knowledgeSources=[]`와 확인 불가 안내예요. 다른 범주·가상 자료·없는 인용 ID·근거 없는 숫자는 허용하지 않아요.

실제 모델 모드는 로컬 RoBERTa로 질문을 먼저 4분류해요. `meta.classification`(선택)은 `{model, label, confidence, ms, usedHistory}`이며 `label`은 `범위 밖`·`사내 규정`·`사내 생활안내`·`수자원공사 정보`예요. 기존 `answer.kind`는 유지하고 가데이터 모드에는 이 메타데이터가 없어요. 범위 밖은 검색/LLM을 호출하지 않고, 규정·회사는 각각 해당 자료 검색과 근거 검사를 거쳐요. 모델·토크나이저·해시 문제는 기존 오류 형식의 `code=AI_CLASSIFIER`, `kind=classifier`, `retryable=false`로 알려요. LLM은 질문 유형을 재분류하지 않고 서버가 분류별 `answer.kind`를 구성해요. JSON 구조·없는 인용 ID·근거 없는 숫자 등의 실패는 기존 `AI_BAD_OUTPUT` 오류로 유지해요.

실제 모델과 가데이터 모두 `apply`·`more`·`missing`을 반환하지 않습니다. 실제 모델은 확인된 내용과 적용 조건, 부족한 근거를 최대 두 문장의 `summary`로 작성하도록 지시받습니다. 회사·사내 생활의 출처는 `knowledgeSources`에서 제공합니다. 가데이터는 추천 질문의 예시를 `meta.mode=mock`으로 반환합니다. 화면에는 ‘시연용 가데이터’를 표시합니다.

`answer.topic`(선택)은 `regulation|company|life`, `answer.evidenceStatus`(선택)는 `found|partial|not_found|refused`예요. 규정·회사·생활 DB 답변은 `meta.classification.label` 옆에 ‘근거 확인’ 또는 ‘근거 확인 불가’를 표시해요. `partial`도 인용 조항이나 문서가 있으면 ‘근거 확인’으로 표시하고, 확인하지 못한 부분은 본문에서 설명해요. 제공 금지 거절은 ‘답변 불가’, 범위 밖은 ‘범위 밖’, 연결·검증 실패는 ‘오류’라는 단일 결과 라벨이에요. 오류는 LLM 출력 상태가 아니에요. 규정은 `found→level=ok`, `partial→unclear`, `not_found→none`, `refused→refused`예요. 규정의 적용 대상은 검색한 원문에서 확인해요. 회사는 `kind=general, source=work`, 생활은 `kind=general, source=intranet`이고 거절·자료 부족은 `knowledgeSources=[]`예요.

사내 생활은 `knowledge.documents.category=사내 생활안내`의 DB 원문을 검색해요. 회사·생활 답변은 실제 인용한 자료만 `knowledgeSources[]`로 반환하고 기존 출처 필드에 `excerpt`(원문 발췌)를 추가해요. 규정·회사·생활 모두 ‘근거 보기’에서 원문·출처를 확인해요. 생활 자료의 가상 여부(`isVirtual`)·제약(`sourceLimits`), 문서 위치·시점·해시·잘림 여부를 유지해요. DB 결과가 없을 때 고정 메뉴로 대체하지 않으며 `intranet[]` 메뉴 표시는 이전 응답 호환용으로 남아요. 범위 밖은 검색·LLM 호출이 없어요.

규정·회사 검색 결과가 없어도 모델에 빈 근거 목록으로 제공 금지 요청 여부를 확인해요. 빈 근거로 `found`·`partial` 답변을 만드는 것은 허용하지 않아요.

`history`의 요청 형식은 그대로예요. 화면은 답변을 받은 최근 5턴을 보내고, 서버는 그중 후속 질문과 이어진 질문 원문 및 답변 본문(`a.summary`)을 턴별로 사용해요. 예전 메뉴형 생활 안내에 본문이 없으면 화면에 표시했던 메뉴 정보를 사용해요. 이전 답변의 `kind`·`level`·실제 출처 ID는 모델 대화에 넣지 않아요. 규정 이름 없이 조항 번호를 물으면 서버는 직전 `basis`로 규정을 찾아 직접 요청한 조항을 우선 전달해요. 조항 참조 단계에서만 직전 규정을 사용했다면 `meta.classification.usedHistory=false`일 수 있어요.

| 요청 | 쓰는 곳 |
| --- | --- |
| `POST /assistant/ask` | 직원 인증 후 본문 `{question, history: [{q, a}]}`을 처리. `history`는 최근 5턴까지 사용. 결과 `{answer, reg, meta}`. 비로그인은 401, 직원 계정이 아니면 403 |
| `GET /jobs/{id}?wait=10` | 챗봇 작업은 요청한 직원만 조회. 응답은 `JobView` |
| `POST /jobs/{id}/cancel` | 챗봇 작업은 요청한 직원만 취소 |

### 부서장 — `team.ts`

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /team/members` · `GET /team/members/{uid}/plans` | 소속 직원 목록 · 직원 기록(공개 범위만). 직원 정보는 이름·사번·소속·직급·직위·부서장 여부만(`TeamUser`), 보고서에서는 심화 질문 결과·목표 달성 답·결과물 첨부를 뺌 |
| `POST /team/plans/{pid}/comments` · `PATCH /team/plans/{pid}/comments/{cid}` | 코멘트 보내기 · 고치기(설계서 밖 추가 · 10/23) |

### 완료 알림 — `notifications.ts` (설계서 밖 추가 · #82)

로드맵 확정(`POST /drafts/{id}/confirm`)과 결과 보고서 작성 작업이 끝나 보고서가 저장된 때(`POST /plans/{id}/reports`의 작업 성공) 서버가 작성한 직원 본인(`audience: 'self'`)과 같은 부서의 부서장(`'head'`)에게 알림을 남겨요. 부서장 본인의 로드맵·보고서는 본인에게만 가요. 직원 계정만 쓸 수 있어요(관리자 403).

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /notifications` | 상단 띠 알림 버튼·목록(30초마다·화면 이동·창 열 때). `{items: AppNotification[] (최근 50건), unread}` — `unread`는 목록 길이와 관계없이 전체 수 |
| `POST /notifications/{id}/read` · `POST /notifications/read-all` | 한 건 읽음(내 알림이 아니면 404) · 모두 읽음. 둘 다 바뀐 목록을 그대로 돌려줌 |

`AppNotification`은 `{id, kind: 'roadmap'|'report', audience: 'self'|'head', employee: {id, name}, planId, planTitle, track, reportId, createdAt, read}`예요. 문구와 이동할 주소는 화면이 정해요(`features/notifications/notificationView.ts`): 본인은 `/roadmaps/{planId}`·`/reports/{reportId}`, 부서장은 `/team/{employee.id}/plans/{planId}`·`/team/{employee.id}/reports/{reportId}`. 확인 전 보고서를 다시 만들면 이전 보고서 알림은 지워지고 새 보고서 알림만 남아요. 부서장 알림은 그 직원이 지금도 같은 부서일 때만 보여요.

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
| 완료 알림 | `api/types/notification.ts` |
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
