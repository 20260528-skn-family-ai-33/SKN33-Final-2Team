# API 계약 (화면이 백엔드에 기대하는 것)

## 관리자 LLM 선택 (#120)

관리자 설정 응답의 `policyStatus`는 정상 시 `active`, 직원별 선택을 끄고 모델을 지정하지 않아 Ollama가 적용된 경우 `default_ollama`다. 설정 파일 형식이 잘못되면 관리자 조회는 `200`과 `{policy: null, level: null, policyStatus: "invalid", ...}`를 반환해 화면에서 새 설정을 저장할 수 있다. 이때 새 모델 실행과 목표 후보 일괄 재생성은 `503 BAD_PROVIDER_POLICY`로 중단된다.

관리자 데이터 관리 화면은 `GET /api/v1/admin/ai-provider`로 현재 정책, 직원별 선택 허용 여부, 서버에 등록한 모델 이름·키 등록 여부·설정 가능 여부를 조회한다. 저장은 `PUT /api/v1/admin/ai-provider`에 `{"policy":"openai"}`, `{"policy":"ollama"}` 또는 베타의 `{"policy":"employee"}`를 보낸다. 고정 모델을 저장할 때 `level`에 지원하는 추론 단계나 `null`(서버 기본값)을 함께 보낸다. 직원별 선택과 `ollama`는 단계를 지정할 수 없다(`ollama`에 단계를 보내면 `422 / BAD_REASONING` · RunPod-Ollama는 늘 추론 없이 부름 · #229). 직원·부서장으로 관리자 API를 사용하면 403, 환경 설정이 빠진 제공자를 저장하면 409를 반환한다. 기본 키는 서버 .env에서 읽는다. 관리자는 `PUT /admin/ai-provider/{provider}/key`에 `{"key":"새 키"}`를 보내 등록하고, `DELETE`로 해제한다. 응답에는 키 원문 없이 `keySource`(env/admin/none), `hasDefaultKey`, `keyConfigured`가 포함된다. 연결 확인은 기존 `GET /api/v1/ai/status?provider=...`를 쓴다.

관리자가 제공자를 고정하면 직원·부서장에게는 해당 모델을 표시하고 제공자·추론 설정 변경 요청은 409를 반환한다. 직원별 선택으로 돌아가면 저장된 개인 선택을 다시 사용한다. 직원 화면은 로그인·새로고침·창 복귀·모델 정보 열기 때 유효한 정책을 읽는다.

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
| 문서에 진행을 적는 작업 | 3안 작성·다시 만들기처럼 서버가 진행 상태를 작성 문서(로드맵 기록)에 적는 일은 202 대신 문서를 바로 돌려주고, 화면이 문서를 다시 읽어 진행을 봄 | `useDraftWatch`·`usePlanWatch` |
| 규정·자료 묶음 | 규정 조항·학습 자료가 나오는 응답에는 화면이 그릴 조항·자료를 `reg`·`res` 묶음으로 함께 보냄(화면이 따로 조회하지 않게) | `mergeReg`·`mergeRes` |
| 작성 문서 자동 저장 | 화면이 고칠 때마다 400ms 뒤 `PATCH /drafts/{id}`로 바뀐 칸만 보냄. `genCur`(3안별 보고 있는 버전)는 바뀐 때만 보냄 | `features/draft/draftSync.ts` |

## 엔드포인트 (영역별)

### 자료 선택 기간 — `/api/v2/drafts/{id}/recommendations/durations`

기간 응답의 `durationEstimates[skill]`은 `resource-hours-books/v3` 기준이다. `startWeek`·`endWeek`·`weeks`는 해당 스킬 자료의 달력 구간이며, 공유 강좌·도서 때문에 다른 스킬과 겹칠 수 있다. 화면 합계는 `weeks`를 더하지 않고 `totalWeeks`를 사용한다. `addedWeeks`는 해당 스킬이 전체 일정에 더한 주차이고, 자료가 없는 스킬은 0주와 null 구간으로 표시한다.

같은 강좌 ID는 전체에서 한 번만 시간에 포함한다. 도서는 고유 ID당 1주이며, 여러 스킬에서 같은 책을 선택하면 첫 배정 구간을 공유한다. `bookWeeks`는 해당 스킬에서 새로 추가한 도서 주차이므로 이미 배정된 책은 0이다. 제목이 같아도 ID가 다르면 별도 도서로 센다. 미확인 강좌 시간의 1주 가정과 숫자로 확보한 추정 시간은 구분한다. `scheduleKey`·`selection`·`skillOrder`·`weeklyHours`로 현재 선택과 계산 결과의 일치를 확인한다. 선택·순서·주당시간이 바뀌면 전체를 다시 계산하고 오래된 결과의 저장을 거부한다. v2 캐시도 다시 계산해야 하므로 백엔드·프런트를 함께 배포한다.

새 계획에는 공유 강좌·도서의 `resourceWindow: {from,to}`, `durationBasis: materials-only`, `totalHUnknown`·`totalHEstimated`가 포함될 수 있다. `totalH`도 같은 강좌·도서 ID는 한 번만 더하지만 활동 ID·소속 스킬은 유지한다. 자료 기간에는 과제 소요 주차가 포함되지 않으며 과제 시간은 `totalH`에 남는다. 기존 확정 계획은 일괄 변경하지 않으며 도서 완료 상태를 함께 갱신하는 변경도 포함하지 않는다.

도서 활동에는 진행 상태를 표시·기록하지 않는다. 로드맵 목록의 `done`·`total`, 보고서의 `doneTitles`·`restTitles`·`executionSnapshot`은 도서를 빼고 계산하며 주차 배정과 메모는 유지한다.

### 스킬별 자료 추천 — `/api/v2/drafts/{id}/recommendations`

조회·생성 응답의 `recommendations.skills[]`에 스킬별 강좌와 도서가 들어간다. 최종 추천 도서는 스킬당 0~3권이며, 0권이면 `books`와 `selectedBooks`가 빈 배열이다. 자료 선택 화면은 저장된 `choices`를 우선한다.

강좌 카드의 선택 필드 `unverifiedTargetTopics: string[]`는 서버가 실제 적용 단원·소개에서 확인하지 못한 세부 목표 범위다. 모든 코스의 자료 카드에서 표시하며 생략·빈 배열이면 안내하지 않는다. 모델이 작성한 값은 사용하지 않는다.

`recommendations.outdated: boolean`은 응답 시 저장된 `retrieval.version`을 현재 코스별 규칙 버전과 비교한 값이다. 버전이 없거나 다르면 이전 기준 안내를 표시한다. 저장 JSON과 기존 선택은 유지하며 자동 재추천하지 않는다. 계획 비교 화면의 ‘해당 계획 다시 생성’으로 새 계획의 자료를 추천받을 수 있다.

스킬에 `courseDiagnostic`과 `bookDiagnostic`이 각각 선택적으로 올 수 있다. 두 필드의 형식은 `{reason, detail, displayDetail?}`이다. `detail`에는 확인 근거 또는 필요한 학습 내용을 담은 원문이 들어간다. `displayDetail`은 원문의 후보 키를 요청에 사용된 자료의 실제 제목으로 바꾼 화면 표시용 문구다. 확인되지 않은 키는 ‘비교 후보’로 표시한다. 두 문자열은 각각 앞뒤 공백을 뺀 길이가 1~240자다. 예산이 부족하면 진단 문장을 보존하고 제목 길이를 줄이거나 중립 표현을 사용한다.

| `reason` | 자료 | 화면에서 설명하는 내용 |
| --- | --- | --- |
| `no_candidates` | 강좌·도서 | 추천에 사용할 후보가 없음 |
| `insufficient_evidence` | 강좌·도서 | 후보의 학습 내용을 확인할 근거가 부족함 |
| `stack_mismatch` | 강좌 | 후보에 명시된 기술이 프로젝트에서 쓰는 기술과 다름 |
| `scope_gap` | 강좌·도서 | 후보가 필요한 학습 범위를 충분히 다루지 않음 |
| `longer_for_coverage` | 강좌 | 짧은 강좌로 충족하기 어려운 범위를 다루기 위해 더 긴 강좌를 추천함 |

자료 선택 화면의 강좌·도서 영역에서 사유와 설명을 표시한다. `displayDetail`이 없으면 `detail`의 후보 키를 ‘비교 후보’로 가려 표시한다. 후보 키가 없는 문장은 그대로 표시한다. 강좌 선택지가 있어도 긴 강좌의 추천 이유나 일부 후보의 부족을 확인할 수 있다. 진단이 없는 기존 응답은 기존 안내 문구를 쓴다.

정상 응답의 스킬별 빈 자료 목록에도 진단 또는 기존 안내를 표시한다. 사유는 현재 추천 응답에서 읽는다.

`{}`는 경로 값. 화면 함수 이름은 `api/endpoints/<파일>`의 이름이에요.

### 계정·내 정보·AI 모드·시연 도구 — `account.ts` (`accountApi`·`aiApi`·`demoApi`)

| 요청 | 쓰는 곳 |
| --- | --- |
| `POST /auth/login` · `POST /auth/logout` · `GET /me` | 로그인·로그아웃·새로 고침 때 계정 |
| `GET /me/workspace` | 로그인 뒤 내 기록 전체(작성 문서·로드맵·보고서) |
| `GET /console/capabilities` | 로그인 전에도 확인 가능한 서버 허용 여부 `{ "picker": true, "demo": false }` |
| `GET /me/profile` · `PUT`/`DELETE /me/profile/self` | 내 정보 |
| `GET /me/goal-suggestions` · `POST /me/goal-suggestions/ensure` · `POST /me/goal-suggestions/regenerate` | 저장된 후보 조회 · 누락/변경 확인 · 명시적 다시 만들기 |
| `GET /ai/providers` · `PUT /me/ai-provider` · `GET /ai/status?provider=` · `GET /ai/log` · `GET /ai/log/{id}` | 좌측 AI 모델 고르기·연결 상태·에이전트 동작 보기(시연·디버그 전용 · 직원·관리자 계정 모두 · 누가 호출했든 모든 계정의 최근 호출을 `employee`(누구의 일)·`by`(관리자 화면에서 시작하면 '관리자')와 함께 줌 · 운영에서는 끔). 목록은 요약과 `callCount`(모델 호출 수)만, `/ai/log/{id}`는 그 기록의 에이전트 입력·출력과 모델 호출마다 보낸 메시지·응답 원문(`calls`)을 자르지 않고 줌(이미지는 개수만). 오래돼 밀려난 기록은 `404 LOG_NOT_FOUND` |
| `PUT /me/reasoning` | AI 모델 창에서 OpenAI 추론 정도 고르기(직원 계정만 · RunPod-Ollama는 `level: null`만 받음) |
| `GET /demo/accounts` | 베타 로그인 직원 선택. `GP5_BETA_ACCOUNT_PICKER=on`일 때만 인증 없이 DB 직원 목록·관리자 로그인 아이디 제공. 비밀번호는 제외 |
| `PUT /me/demo-settings` · `POST /demo/reset` · `POST /demo/jump` | 시연 전용(가데이터·실패 시연·단계 이동·초기화) |

초기화와 단계 이동은 로그인한 직원의 단계 이동으로 생성한 프로젝트만 교체합니다. 출처가 표시되지 않은 기존 기록과 실제 코멘트를 받은 로드맵은 보존합니다. 기존 작성 중인 로드맵과 시연 초안이 겹치면 `409 EXISTING_DRAFT`를 반환하고 이전 상태를 유지합니다. 코멘트 예시는 화면에서만 열리며 기존 클라이언트의 `stage: "comment"` 요청은 기록·알림 생성 없이 `{"entry":"home"}`을 반환합니다.

단계 이동으로 만든 초안은 조회 응답의 `draft.demoSeeded`가 `true`입니다. 서버가 저장한 출처만 사용하며 확정 후에도 시연 초기화 대상입니다. 이 초안은 `together`와 `after`로 확정할 수 있고 부서장에게 확정 알림을 보내지 않습니다. `{"startMode":"archive"}`는 `409 DEMO_ARCHIVE_FORBIDDEN`으로 거절해 기존 로드맵과 수정안을 보존합니다. 시연 도구가 켜져 있어도 직원이 직접 생성한 초안에는 일반 확정 규칙이 적용됩니다.

`GP5_BETA_ACCOUNT_PICKER`는 시연 모드와 독립적입니다. 베타 예시는 on이며, 미설정 또는 off이면 `GET /demo/accounts`는 DB 조회 전에 `404 / NOT_FOUND`를 반환하고 화면에서 직원 선택을 숨깁니다. 베타 종료 시 off로 변경하고 백엔드를 다시 생성한 뒤 화면을 새로고침합니다. on일 때도 비밀번호를 반환하지 않으며 직원 선택은 사번만 채웁니다. 직접 입력 로그인은 어느 설정에서도 유지합니다.

브라우저 콘솔은 API 요청의 `X-GrowPath-Picker: off`, `X-GrowPath-Demo: off`로 해당 기능을 끕니다. 시연이 허용된 환경에서는 `X-GrowPath-Timeout`(1~900초), `X-GrowPath-Input`(1~131072토큰), `X-GrowPath-Output`(1~32768토큰)을 모델 호출과 해당 요청이 시작한 작업에 적용합니다. 범위 밖의 값은 `422 / INVALID_CONSOLE_OPTION`입니다. 시연 모드에서는 `X-GrowPath-Ollama-Url`과 `X-GrowPath-Ollama-Key`로 같은 요청의 Ollama 주소와 Bearer 키를 지정합니다. 주소를 지정하고 키를 생략하면 해당 Pod에는 인증 없이 연결합니다. 두 헤더를 모두 생략하면 서버 주소와 키를 사용합니다.

`GP5_DEMO_MODE=off`이면 위 시연 전용 3개 API와 `GET /ai/log`·`GET /ai/log/{id}`는 인증·조회 전에 `404 / NOT_FOUND`를 반환합니다. 직원·관리자 모두 같은 제한을 받습니다. `GET /me`와 실행 컨텍스트는 off에서 저장된 `demo_mock`·`fail_sim`을 무시하고 `demoMock: false`, `failSim: {}`를 사용하며 DB 원본·선택한 AI 제공자·추론값은 유지합니다.

`GET /ai/providers`에는 서버 시연 허용 여부인 최상위 `demoMode: boolean`이 추가됩니다. 예를 들어 `{ "current": "ollama", "demoMode": false, "providers": [...], "docLibs": {...} }`이면 화면은 시연 도구와 관리자 가데이터 선택지를 숨깁니다. 값이 없거나 조회가 실패해도 표시하지 않습니다. 서버 `GP5_DEMO_MODE`와 프런트 `VITE_DEMO_TOOLS`는 미설정·빈 값·공백·알 수 없는 값이면 off이며, 앞뒤 공백과 대소문자를 정리한 on만 허용합니다. 서버는 빈 환경변수도 파일 설정보다 우선합니다. 브라우저는 `VITE_DEMO_TOOLS`를 시연 모드의 초기값으로 사용하며 콘솔의 `demo on/off`로 변경할 수 있습니다. 서버가 허용하고 브라우저 시연 모드가 켜져야 시연 도구와 개인 모델 설정이 활성화됩니다. 직원의 미설정 AI 기본값은 `ollama`이며 OpenAI 키 설정만으로 선택이 바뀌지 않습니다.

시연 설정 저장은 서버가 성공 응답을 보낸 뒤에만 화면에 반영합니다. 가데이터·실패 시연 저장은 같은 큐에서 요청하고, 실패 시 기존값을 유지합니다. 이전 로그인 회차의 응답은 버리며 시연 응답으로 제공자·추론값을 덮지 않습니다.

서버 ON·프런트 OFF에서 직원이 AI 모델 메뉴의 해제를 누르면 기존 `PUT /me/demo-settings`에 `demoMock: false`와 지원하는 모든 `failSim` 항목의 `false`를 한 번에 보냅니다. 버튼은 적용 중인 시연 설정이 있을 때만 표시합니다.

`GET /ai/providers`의 `providers[].models`는 `{default, roadmap, regulation, embed, vision}`이에요. `default`는 진단 에이전트, `roadmap`은 로드맵 에이전트, `regulation`은 규정 에이전트(사내 생활 도우미 답변), `vision`은 기획서 이미지 읽기 모델이에요. `regulation`이 없는 옛 응답이면 화면은 `default`를 써요. `GET /ai/status?provider=ollama`의 `models[]`는 `{role, name, installed, loaded}`이고(예전의 `think` 필드는 #229에서 없앴다), `default` 다음에는 `default`와 이름이 다른 `roadmap`·`regulation`만 들어가요(같은 이름이면 Ollama에 한 번만 올라가서) (#33).

추론 정도 요청은 `{ "provider": "ollama" | "openai", "level": "<단계 이름>" | null }`이고 그 모드의 값만 바꿔(다른 모드 값은 그대로 · 동시에 저장해도 사라지지 않음) 모드별로 저장한 전체 `{reasoning: {ollama?, openai?}}`를 돌려준다. 화면은 저장을 하나씩 차례로 보내고 마지막 선택의 응답만 화면에 맞춘다. `null`은 그 모드를 서버 기본값으로 되돌린다. 단계 이름은 소문자·숫자·`_`·`-` 20자 이내만 받고 `true`·`false` 같은 값은 받지 않는다(`422 / BAD_REASONING`). OpenAI는 서버의 단계 목록 밖이면 같은 오류다. **`ollama`는 `level: null`만 받고, 단계 이름을 보내면 `422 / BAD_REASONING`(RunPod-Ollama는 추론 없이만 답함)이다.** 고를 수 있는 단계는 이렇게 온다.

- OpenAI: `GET /ai/providers`의 openai 항목 `reasoning: {levels, default, modelDefault}`. `levels`는 `.env`의 `OPENAI_REASONING_LEVELS`이고 비면 기본 모델 gpt-6-luna의 코드 값(`none`~`xhigh`)이다(다른 모델이면 빈 목록 = 고르지 못함). `default`는 `.env`의 `OPENAI_REASONING_EFFORT`(비면 `null` = 보내지 않음), `modelDefault`는 보내지 않을 때 모델이 쓰는 값(gpt-6-luna `medium` · 모르는 모델이면 `null`)이고 화면 '기본값 · 보통' 표시에만 쓴다.
- RunPod-Ollama: 고를 단계가 없다. `GET /ai/providers`의 ollama 항목은 `reasoning: {levels: [], default: "off"}`이고, 화면은 드롭다운 없이 '추론 없음'만 보인다(#229).

직원이 고른 값은 `GET /me`·`PUT /me/demo-settings` 응답의 `reasoning`으로 온다. OpenAI는 고른 값 → `.env` 기본값 순으로 `reasoning_effort`에 보내고, 둘 다 없으면 보내지 않아 모델 기본값을 따른다. **RunPod-Ollama는 진단·로드맵·규정·이미지 읽기 모든 호출에 고른 값·`.env`와 관계없이 늘 `think: false`를 보낸다(#229).** 예전에 저장된 `reasoning.ollama` 값이나 관리자 정책 파일의 `ollama` 단계는 읽지 않는다. 이미지 읽기 모델에는 직원 값을 쓰지 않는다. 관리자 고정 모델의 목표 후보도 관리자 추론 단계를 사용하며(RunPod-Ollama는 단계 없음 · 기본 `off`), 미지정 시 서버 기본값을 따른다.

근무성적평정은 내 정보와 목표 추천에서 제외한다. 호환용 응답 배열 `evaluations`와 `view.evals`는 비어 있다. 개인 입력의 `devYears`가 숫자로 바뀌지 않거나 0~50년 범위를 벗어나면 `422 / DEV_YEARS_RANGE`를 반환하고 기존 입력을 보존한다. #15의 격리 DB·실제 인증 API 검사로 확인했다.

업무 설명(`view.profile.workDesc`·`self.profile.workDesc`)은 `employees.planned_project_description`에서 읽고 같은 열에 저장한다. 빈 값은 NULL이며 최대 500자(`422 / WORK_DESC_LENGTH`)다. 프로젝트는 기존 `employee_input_profiles.project_experience`의 줄바꿈 목록을 사용한다. 둘 다 선택이므로 프로젝트만 입력해도 저장·맞춤 추천이 가능하다. 새 테이블/열은 추가하지 않는다. 새 저장은 `edited.workDesc`를 만들지 않고 처음 값과 변경 해시만 보존한다.

무변경 저장은 원래 입력 프로필 행과 갱신 시점을 보존한다. 업무 설명만 고쳐도 빈 입력 프로필을 만들지 않는다. 되돌리기는 본인이 고친 설명을 처음 값으로 복원하되 기술만 고쳤거나 이후 관리자가 갱신한 설명은 덮지 않는다. 구판 `edited.workDesc`는 명시적 저장/이관 전까지 읽기 호환을 유지한다. 선택 이관 SQL `backend/db/migrate_self_work_descriptions.sql`은 팀 열과 충돌하면 전체 롤백하며 구판 사본에 없던 처음 설명을 추정하지 않는다. 부서장 응답에는 본인 입력을 보내지 않는다.

`POST /auth/login`과 `GET /me`는 목표 생성 요청이나 추천 입력 해시 검사를 하지 않는다. 본인 입력 저장/되돌리기·관리자 수정/업로드의 **저장 성공 뒤 추천 입력 해시가 바뀐 직원만** 백그라운드로 갱신한다. 부서명·상위 부서 변경은 해당/직속 하위 부서의 직원, 보유 자격명 변경은 연결된 직원도 포함한다. 무변경 저장과 저장 실패는 재생성하지 않는다. 목표 화면의 `ensure`는 생성 기록·후보가 모두 없는 계정만 처음 준비하며 기존 후보·실패 상태·설정용 mock 후보를 자동 재생성하지 않는다. 생성 중 정보가 바뀌면 옛 결과는 저장하지 않고 지정 모델로 최신 입력을 준비한다. 실패하면 기존 후보를 보존하고 수동으로 재시도한다. `regenerate`는 명시적 다시 만들기이며 SQL 직접 수정 후에도 사용한다. 배포 전에 사전 생성 도구로 준비할 수 있다.

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
| `POST /drafts/{id}/education-guide` | 본인의 3안 생성 화면 최초 진입 시 빈 본문으로 요청. 초안에 저장한 `{basis: {name, article, text, page, version, chunkId} ∣ null}`을 재사용. 초안 생성 전이나 계획 생성 전에는 404 또는 409. |
| 기존 안별·수정안별 지원 조건 재시도 | 410 `SUPPORT_RETIRED` |
| `POST /drafts/{id}/selection` · `POST /drafts/{id}/confirm` | 안 고르기 · 확정(→ `{planId}`). 확정 본문은 선택 `{startMode: together \| after \| archive}`이고, 진행 중인 로드맵이 있을 때만 의미가 있어요. 없으면 `together`(함께 진행), `after`는 모두 끝난 다음 주를 `plan.startDate`에 저장(이미 지났으면 저장 안 함), `archive`는 진행 중인 로드맵을 확정과 같은 트랜잭션에서 보관해요. 다른 값은 422 `BAD_START_MODE`. 화면은 작성 탭에 들어올 때 고른 값을 작성 문서의 `startMode`로 자동 저장(`POST`·`PATCH /drafts`, 잘못된 값은 같은 422)했다가 확정 때 보내요 |

### 확정 로드맵·점검·보고서 — `plans.ts`

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /plans/{id}` · `PUT /plans/{id}/activities/{act}/progress` | 로드맵 읽기 · 활동 기록(완료·메모) |
| `POST /plans/{id}/activities/{act}/attachments` | 결과물·수료증 첨부(사후 점검 파일도 `act='post'`로 같은 곳) · 본인의 진행 중 로드맵과 그 로드맵의 활동만(아니면 404·409) |
| `POST /plans/{id}/archive` · `.../resume` | 보관·다시 진행 |
| `POST /plans/{id}/revisions` · `POST /revisions/{rid}/accept` · `DELETE /revisions/{rid}` | 수정 요청(작업) · 수정안 확정 · 버리기 |
| `POST /plans/{id}/comments/{cid}/read` | 부서장 코멘트 읽음 |
| `PUT /plans/{id}/post-assessment` · `POST .../post-assessment/deep` | 사후 점검 저장(`{quizAnswers?, answers?, goalSelf?, file?, clearFail?, deepMcq?, deepEssay?}` → `{plan, res, reg}`) · 심화 질문 사후 문제(작업 · 설계서 밖 추가 10/23). 사후 퀴즈 정답·해설은 제출 전에는 숨기고, 보고서 작성을 시작(`post.submitted=true`)하거나 완료한 뒤에만 공개해요. 제출 뒤에는 퀴즈 답안을 바꿀 수 없어요(409 `POST_LOCKED` · 작성 중 저장은 409 `REPORT_BUSY`) |
| `POST /plans/{id}/reports` · `GET /reports?planId=` · `POST /reports/{rid}/confirm` | 보고서 만들기(비동기 202 `{jobId, status: 'running', submitted: true, quizSurvey?}`) · 목록 · 확인 |

보고서(`Report`)의 `opt`는 코스 ID(A1~A3)예요. 화면은 `trackName(opt)`로 Free·Crash·Challenge Course 이름을 보여 줘요. 이전 보고서에 저장된 Track 이름(Free·Fast·Challenge Track)은 서버가 코스 ID로 바꿔 보내요. 보고서 목록, `GET /me/workspace`, 부서장의 직원 기록 응답에 모두 적용돼요(#78).

### 학습 자료·자격증·규정·스킬 지도 — `catalog.ts`

`GET /resources`·`POST /resources/lookup`·작업 공간의 자료 첨부는 요약(`detailsLoaded=false`)이다. `content`는 최대 400자, `curriculum`에는 개수(`item_count`)·확보 상태(`coverage`)만 보내고 `items`는 제외한다. `GET /resources/{id}`는 상세(`detailsLoaded=true`)로 전체 소개와 순서 있는 `curriculum.items`(`title`, `section`, `description`)를 제공한다. 목차 유무·자료 유형과 관계없이 요약에 ‘전체 소개·상세 보기’ 링크를 제공한다. 상세 화면은 전체 상세 캐시가 있어도 재진입마다 단건 상세를 조회하며 이후 요약 수신으로 전체 목차를 지우지 않는다.

`curriculum.coverage`는 `public_outline`·`partial_outline`·`sample`·`description_only`·`full_outline`이며 목차를 확보하지 못한 것을 빈 강좌로 해석하지 않는다. `full_outline`은 사내교육의 전체 실습 계획에 사용하며 원문 강의 전체나 자막을 저장했다는 뜻은 아니다.

강좌 `difficulty`는 초급·중급·중상·고급(`BEGINNER`·`INTERMEDIATE`·`UPPER_INTERMEDIATE`·`ADVANCED`)이며 화면에는 등급만 표시한다. API와 추천 후보에는 출처(`difficultySource`: `original`·`estimated`·`reviewed`), 추정 여부(`difficultyEstimated`), 근거(`difficultyBasis`)를 유지한다. `difficultyEstimated=true`일 때만 `estimated`에 `difficulty`를 넣는다.

도서는 ISBN에 연결된 공개 도서 페이지를 `url`로 제공한다. 이전 추천·확정 계획·과거 버전의 수집 API 링크는 응답 사본에서 교체하고 저장 원문과 선택은 보존한다. 사내교육의 `url`은 `/resources/{id}?view=curriculum`으로 안내·교육비·시간·펼친 실습 목차를 제공한다. 앱이 배포한 사내교육 WebP와 일반 자료 SVG 표지도 허용하며 임의의 상대 경로는 허용하지 않는다. Crash 전용 핵심 결과물 표시는 제거하지만 기존 `coreOutcome`·`coreCriteria`·`followUpScope` 저장 필드는 유지한다.

`hours`는 일정 계산용 정밀 값이고 `timeStatus`는 `confirmed`·`estimated`·`manual`이다. `durationKind`로 영상/학습 시간을 구분하고 `timeNote`에 출처·추정 근거를 제공한다. 자료·단계·선택지·간트·실행 기록·수정 화면은 공통 함수를 통해 10분 단위로 반올림한다(예: `5.83333` → ‘5시간 50분’). 새 `roadmap_steps.estimated_duration` 문구도 같은 규칙이며 숫자와 일정 계산 정밀도는 유지한다. 관리자 입력에서 시간 숫자는 그대로 두고 시간 추정 표시만 해제해도 `manual`로 저장하고 자동 동기화에서 보존한다. 새 로드맵 활동은 `hoursEstimated`, `hoursBasis`를 함께 저장하며 기존 확정 활동의 시간을 일괄 변경하지 않는다. 과거 활동의 `hoursEstimated`가 없으면 ‘추정 여부 미기록’으로 표시한다. 현재 강좌 시간이 확인돼 있어도 과거 계획 시간을 확인 시간으로 재해석하지 않는다. 025·026 DB 적용과 적재 후 앱을 배포해야 한다.

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /certifications` | 자격증 2단계 고르기 |
| `GET /resources?kind=&q=&limit=&offset=` · `POST /resources/lookup` · `GET /resources/{id}` | 학습 자료 목록(30개씩)·여러 개 조회 |
| `GET /regulations/sets` · `POST /regulations/lookup` | 직원 구분별 규정 묶음 · 조항 조회 |
| `GET /skills/map` | 스킬 지도(설계서 밖 추가 · 10/23) |

### 사내 생활 도우미 — `assistant.ts`

챗봇은 관리자가 지정한 제공자를 사용합니다. 베타의 직원별 선택에서는 로그인한 직원의 AI 설정을 따릅니다. 직원 ID는 작업 소유권과 호출 기록에 사용합니다. 모델에는 빈 사용자 상황을 전달하고, 규정 원문의 적용 대상과 질문·앞 대화에 적힌 조건을 사용합니다. 브라우저 대화는 직원별로 분리합니다.

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
| `GET /team/members` · `GET /team/members/{uid}/plans` | 소속 직원 목록 · 직원 기록(공개 범위만). 직원 정보는 이름·사번·소속·직급·직위·부서장 여부만(`TeamUser`), 보고서에서는 심화 질문 결과·목표 달성 답·결과물 첨부를 뺌. 확인 전 표시(#96): 목록의 직원마다 `unseenPlans`·`unseenReports`, 직원 기록에 `unseen: {plans, reports}`(id 목록) — 부서장이 아직 읽지 않은 그 직원의 로드맵·보고서 알림 기준 |
| `POST /team/plans/{pid}/comments` · `PATCH /team/plans/{pid}/comments/{cid}` | 코멘트 보내기 · 고치기(설계서 밖 추가 · 10/23) |

### 결과 보고서 과제 — `tasks.ts` (설계서 밖 추가 · #96)

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /team/plans/{id}/tasks` · `GET /plans/{id}/tasks` | 부서장(소속 직원의 로드맵만) · 직원(본인 로드맵만)의 과제 목록. `{tasks: ReportTask[]}` |
| `POST /team/plans/{id}/tasks` `{body}` | 부서장이 과제 보내기(2000자까지). 바뀐 목록을 돌려줌. 빈 내용 400 · 보고서가 없는 로드맵 409 |
| `POST /plans/{id}/tasks/{taskId}/submit` (multipart `answer`·`file`) | 직원이 결과 제출(글 4000자 · 파일 15MB까지, 둘 중 하나 필수). 바뀐 목록을 돌려줌. 빈 제출 400 · 이미 제출 409 · 파일 초과 413 |
| `GET /plans/{id}/tasks/{taskId}/file` · `GET /team/plans/{id}/tasks/{taskId}/file` | 제출 파일 내려받기(첨부로만 보냄) |

`ReportTask`는 `{id, planId, body, createdAt, head: {id, name}, submittedAt, answer, file: {name, size} | null}`예요(`api/types/task.ts`).

### 완료 알림 — `notifications.ts` (설계서 밖 추가 · #82)

어떤 일이 생기면 누구에게 알릴지는 서버가 정해요(#96). 직원 계정만 쓸 수 있어요(관리자 403).

| 일 | 받는 사람(`audience`) | `kind` |
| --- | --- | --- |
| 로드맵 확정(`POST /drafts/{id}/confirm`) | 같은 부서의 부서장(`head`). 본인에게는 보내지 않아요 | `roadmap` |
| 결과 보고서 작성 작업이 끝나 저장됨(`POST /plans/{id}/reports`) | 본인(`self`)·부서장(`head`). 부서장 본인의 보고서는 본인에게만 | `report` |
| 오래 걸리는 작업이 끝남·실패(`jobKind`: 3안 `options`·다시 만들기 `regenerate`·학습 자료 `materials`·수정안 `revision`, 보고서 `report`는 실패만) | 본인(`self`) | `job` |
| 부서장이 새 코멘트를 보냄(고칠 때는 보내지 않아요) | 그 직원(`member`) | `comment` |
| 부서장이 결과 보고서 과제를 보냄 | 그 직원(`member`) | `task` |
| 직원이 과제 결과를 제출함 | 과제를 낸 부서장(`head`) | `task_result` |

3안·학습 자료처럼 안·코스별로 나뉜 작업은 모두 끝났을 때 한 번만 알려요. 사용자가 멈춘 작업은 알리지 않아요. 로드맵을 수정해도(수정안 확정) 부서장에게 알리지 않아요.

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /notifications` | 사이드바 하단 알림 버튼·목록(30초마다·화면 이동·창 열 때)과 새 알림 하단 플로팅(#96, #190). `{items: AppNotification[] (최근 24시간 이내 알림 최대 50건 · 읽지 않은 알림 우선), unread}` — `unread`는 목록 길이와 관계없이 최근 24시간 내 읽지 않은 전체 수. 읽은 알림도 24시간 동안 목록에 남음(#190) |
| `POST /notifications/{id}/read` · `POST /notifications/read-all` | 한 건 읽음(내 알림이 아니면 404) · 모두 읽음. 둘 다 바뀐 목록을 그대로 돌려줌 |
| `POST /notifications/read-target` `{kind: 'roadmap'\|'report', id}` | 부서장이 직원의 로드맵·보고서 화면을 열 때(#96). 그 대상의 내 알림을 모두 읽음으로 바꾸고 바뀐 목록과 `changed`(바뀐 수)를 돌려줌. 잘못된 종류 400 · 형식이 틀린 id 404 · 읽을 알림이 없으면 `changed: 0` |

`AppNotification`은 `{id, kind: 'roadmap'|'report'|'job'|'comment'|'task'|'task_result', audience: 'self'|'head'|'member', employee: {id, name}, planId, planTitle, track, reportId, draftId, commentId, taskId, jobKind, jobStatus: 'done'|'failed'|null, createdAt, read}`예요(읽은 알림도 24시간 동안 목록에 남으며 `read`는 `boolean`). `employee`는 알림을 일으킨 사람이고(코멘트 알림이면 보낸 부서장), `planId`는 로드맵 확정 전 작업(`options`·`regenerate`·`materials`)만 `null`이에요. 문구와 이동할 주소는 화면이 정해요(`features/notifications/notificationView.ts`): 본인은 `/roadmaps/{planId}`·`/reports/{reportId}`, 부서장은 `/team/{employee.id}/plans/{planId}`·`/team/{employee.id}/reports/{reportId}`, 코멘트는 `/roadmaps/{planId}/comments`, 작업은 `/new/options`·`/new/materials`·`/roadmaps/{planId}/revise`·`/roadmaps/{planId}/post`. 본인·직원 알림이 가리키는 화면을 이미 보고 있으면 화면이 바로 읽음으로 바꿔요. 확인 전 보고서를 다시 만들면 이전 보고서 알림은 지워지고 새 보고서 알림만 남아요. 부서장 알림은 그 직원이 지금도 같은 부서일 때만 보여요.

### 관리자 — `admin.ts` (5차 목업에서 추가 · 2026-10-21 사용자 결정 · 설계서 반영 여부는 사람 확인 필요)

| 요청 | 쓰는 곳 |
| --- | --- |
| `GET /admin/overview` | 개요 |
| `GET /admin/datasets/{ds}/rows?sheet=&q=&limit=&offset=` | 데이터 표(`ds`: hr·education · 규정은 표로 다루지 않음) |
| `POST /admin/datasets/{ds}/edit` | 한 건 고치기. 본문 `{rows}`면 확인만(바뀌는 칸·오류·`token`), `{rows, save:true, token, goalMode}`면 저장 |
| `GET /admin/datasets/{ds}/export?format=&sheet=` · `.../template?...` | 엑셀·CSV 내려받기(링크로 염) |
| `POST /admin/datasets/{ds}/preview`(파일) · `GET /admin/uploads/{id}` · `POST .../apply` · `DELETE /admin/uploads/{id}` · `GET /admin/uploads?dataset=` | 파일 미리보기 · 다시 보기 · 반영 · 취소 · 이력 |
| `GET /admin/goal-suggestions/employees` | 목표 후보를 다시 만들 직원 고르기(재직 직원 · 지금 후보 상태와 만든 모드) |
| `POST /admin/goal-suggestions/regenerate-all` | 목표 후보 다시 만들기. 화면은 `{expectedPolicy, expectedLevel, employeeIds?}`를 보낸다. 고정 모델은 해당 제공자, 직원별 선택은 직원의 설정을 사용한다. 확인한 정책이 바뀌면 409. `employeeIds`가 있으면 그 직원만(재직 직원만 받음 · 없으면 400 `NO_EMPLOYEES`). 고른 모델을 지금 쓸 수 없으면 409 `AI_UNAVAILABLE` |
| `GET /admin/regulations` | 규정 데이터 '지금 규정': 도우미가 쓰는 버전의 규정 목록(`id`·`name`·`group`·`version`·`effective`·`fileName`·`size`·`available`). 규정이 많은 직원 구분부터 |
| `GET /admin/regulations/{id}/pdf` | 지금 규정 원문 PDF 내려받기(링크로 염 · 서버에 원문이 없으면 404 `NO_PDF`) |
| `POST /admin/regulations/uploads`(파일 `file` + `memo`) · `GET /admin/regulations/uploads` | 새 규정 PDF 올리기(PDF만 · 20MB · 메모 500자 · 201) · 올린 PDF 목록(처리 상태 없음) |
| `GET /admin/regulations/uploads/{id}/pdf` | 올린 PDF 내려받기 |
| `DELETE /admin/regulations/uploads/{id}` | 잘못 올린 PDF 지우기(서버 파일과 기록을 함께 · 되돌릴 수 없음 · 204, 없으면 404 `NO_UPLOAD`) |

서버 시연 모드가 off일 때 관리자 목표 생성의 `mode: "mock"`과 직원 수정·자료 반영의 `goalMode: "mock"`은 `409 / DEMO_DISABLED`입니다. 예: `{ "error": { "code": "DEMO_DISABLED", "message": "시연 모드가 꺼져 있어 가데이터로 만들 수 없어요", ... } }`. 저장·작업 생성 전에 거절하고 실제 모델로 자동 전환하지 않습니다. 관리자 일괄 생성의 초기 선택은 `ollama`, 수정·자료 반영은 기존 직원 선택을 따릅니다. 이전 화면에 남은 mock 선택은 다시 고르도록 안내하고 실행을 막습니다. on에서만 명시적인 가데이터 생성을 허용합니다.

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
