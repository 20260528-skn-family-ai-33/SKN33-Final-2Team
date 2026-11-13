# 챗봇 질문 분류 모델 연결

## 파일별 역할

| 파일 | 역할 | 실행 시점 |
| --- | --- | --- |
| [`app/question_classifier.py`](app/question_classifier.py) | `.pt` 모델·토크나이저 로딩과 질문 4분류 | 실제 모드에서 챗봇 질문 처리 시 |
| [`app/knowledge.py`](app/knowledge.py) | 회사 정보·사내 생활 범주별 DB 원문·벡터 검색 | 회사·생활 질문 처리 시 |
| [`app/agents/regulation.py`](app/agents/regulation.py) | 분류별 검색·출처/숫자 검증·API 응답 구성 | 챗봇 질문 처리 시 |
| [`app/agents/grounded_answer.py`](app/agents/grounded_answer.py) | 질문 재분류 없이 근거 상태·요약·인용 생성 | 규정·회사·생활안내 답변 시 |
| [`app/errors.py`](app/errors.py) | 모델 연결 실패 원인과 조치 안내 | 오류 발생 시 |
| [`tests/test_question_classifier.py`](tests/test_question_classifier.py) | 연결 경로·파일 누락·실패 처리 단위 테스트 | 아래 테스트 명령을 직접 실행할 때만 |
| [`tests/test_regulation_follow_up.py`](tests/test_regulation_follow_up.py) | 조항 이어 묻기·최근 5턴의 질문과 답변 전달 회귀 테스트 | 아래 테스트 명령을 직접 실행할 때만 |
| [`tools/check_classifier.py`](tools/check_classifier.py) | 실제 모델 로딩과 대표 질문 4개 분류 확인 | 아래 확인 명령을 직접 실행할 때만 |
| [`../requirements.txt`](../requirements.txt) | CPU 추론 패키지 버전 | 의존성 설치·Docker 이미지 빌드 시 |
| [`models/classifier-manifest.json`](models/classifier-manifest.json) | 모델·토크나이저 해시와 학습 라벨·입력 길이 | 모델을 처음 로드할 때 |

검증용 Python 파일은 보관하며, 챗봇 사용이나 서버 시작 때 자동으로 실행하지 않아요. 실제 요청에서 동작하는 것은 학습이 끝난 모델의 **추론**이에요. 재학습은 하지 않아요. 모델 로딩 때의 파일 해시·라벨 확인은 실행 코드에 남아 있는 연결 보호 절차예요.

학습 코드·데이터·평가 기록은 [Chatbot_classification 실험 자료](models/Chatbot_classification/README.md)에 있어요. 분류기는 `models/` 바로 아래의 실행 파일을 읽어요.

## 챗봇 처리 흐름

로그인한 직원의 질문은 **1~5단계**로 처리해요. 1·2단계는 공통이며, 3~5단계는 사내 규정(`-1`)과 사내 생활안내·수자원공사 정보(`-2`)로 나뉘어요. `3-1`과 `3-2`는 질문 유형에 따른 분기이며 한 질문에서 두 경로를 차례로 실행하는 번호가 아니에요.

| 단계 | 처리 | 함수 |
| --- | --- | --- |
| 1단계 | 모든 질문의 직원 구분 확인 후 RoBERTa 질문 분류 | `classify_question_roberta` |
| 2단계 | 분류 확신도에 따라 라벨 확정 또는 LLM 재분류 | `verify_or_reclassify_label_with_llm`, `classify_label_with_llm` |
| 3-1단계 | 사내 규정 RAG 근거 검색·조항 선택 | `retrieve_regulation_slots` |
| 4-1단계 | 사내 규정 근거를 바탕으로 LLM 답변 생성 | `generate_regulation_summary` |
| 5-1단계 | 사내 규정 답변 검증·최종 응답 구성 | `format_regulation_response` |
| 3-2단계 | 사내 생활안내·수자원공사 정보 RAG 근거 검색 | `retrieve_knowledge_slots` |
| 4-2단계 | 사내 생활안내·수자원공사 정보 근거로 LLM 답변 생성 | `generate_knowledge_summary` |
| 5-2단계 | 사내 생활안내·수자원공사 정보 답변 검증·최종 응답 구성 | `format_knowledge_response` |

2단계의 두 함수는 하나의 처리 단계를 나눠 맡아요. `verify_or_reclassify_label_with_llm`은 확신도로 재분류 필요 여부를 판단하고, 필요할 때만 보조 함수 `classify_label_with_llm`이 LLM 호출과 응답 라벨 검증을 수행해요. 별도의 2-1·2-2단계나 두 번의 LLM 재분류가 아니에요. 80% 기준은 개별 질문의 예측 확신도이며 모델 전체의 예측 정확도가 아니에요.

기존 3·4·5단계 표기는 각각 3-1·4-1·5-1단계로, 기존 6·7·8단계 표기는 각각 3-2·4-2·5-2단계로 맞춰요. `answer_with_pipeline`이 분류 결과에 맞는 경로를 실행하며, 직원 구분 확인을 통과한 뒤 범위 밖으로 확정한 질문은 검색과 답변 생성 없이 종료해요.

로드맵과 같은 계정별 AI 설정으로 OpenAI 또는 Ollama를 선택해요. 가데이터 모드에서는 추천 질문의 고정 예시를 ‘시연용 가데이터’로 표시하고, 준비되지 않은 질문은 별도로 안내해요. 시연 답변에는 실제 검색·모델 호출이 없어요.

챗봇은 로그인 세션과 작업 소유권을 확인해요. 질문 제출은 `POST /assistant/ask`, 결과 조회와 취소는 기존 `/jobs/{id}` 경로를 써요. 챗봇 작업의 결과는 요청한 직원에게만 보여요. 직원 ID는 작업과 호출 기록에 남고, 모델의 사용자 상황은 빈 객체예요. 브라우저의 대화는 직원별로 분리해요.

실제 모델 모드에서는 직원 구분을 사내 도우미의 공통 필수 정보로 확인해요. **사내 규정·수자원공사 정보·사내 생활안내·범위 밖 질문 모두** 1단계에서 로그인한 직원의 직원 구분을 먼저 확인해요. `profile.employee_group()`이 `None`, 빈 문자열 또는 공백만 반환하면 RoBERTa 분류·검색·LLM 호출 전에 동일한 `EMPLOYEE_GROUP_UNAVAILABLE` 오류로 종료해요. 화면에는 “로그인한 직원의 직원 구분을 확인할 수 없어요”와 “인사 담당 부서에 직원 구분 등록 여부를 확인해 주세요”를 안내해요. 질문이나 이전 대화에 직군이 적혀 있어도 누락된 로그인 직원 정보를 대신하지 않아요.

이는 회사 정보·생활안내의 검색 필터에 직원 구분이 필요한지와 별개로, 직원 구분 누락을 질문 유형과 관계없이 알리려는 공통 진입 정책이에요. 회사 소개·구내식당 위치·범위 밖 질문도 직원 구분 없이 계속 처리하지 않도록 한 의도된 동작이며, 누락 검사를 규정 분기로 제한하지 않아요. 가데이터 모드는 실제 분류 파이프라인을 실행하지 않는 별도 시연 경로예요.

1단계의 조회 직군은 현재 질문에 명시한 직군 → 관련된 후속 대화에서 계승한 직군 → 로그인 계정의 직군 순으로 결정해요. 새 주제나 관련 없는 독립 질문에서는 계승을 초기화해요. 현재 명시 직군 감지는 일반직·실무직·운영직을 대상으로 하며, 질문의 명칭 포함 여부를 사용하는 기존 방식이에요. 복수 직군 비교나 명칭 경계 판별은 이번 슬롯 배분 변경에서 추가하지 않아요. 통합 파이프라인은 결정한 조회 직군을 검색에 전달하고 로그인 프로필 원본은 바꾸지 않아요.

규정 검색은 이 조회 직군의 규정 묶음을 사용하고 각 조항의 `appliesTo`를 모델에 전달해요. 국외근무 자료는 해당 직군에 등록되어 있고 관련 질문일 때 검색에 포함해요. 다른 사용자 조건은 질문과 연결된 이전 대화에서 확인해요. [이슈 #68](https://github.com/20260528-skn-family-ai-33/SKN33-Final-2Team/issues/68)

3-1단계의 기본 근거 예산은 핵심 4개·부모 문맥 최대 2개·직접 참조 문단 최대 1개로 총 7개입니다. 명시 조항을 먼저 보존하고 현재 질문 단독 검색의 상위 유효 후보 2개를 이전 답변 근거보다 앞세웁니다. 이전 근거는 최대 1개만 보충하고 나머지 핵심 자리는 검색 후보로 채웁니다. 부모 문맥은 문서 전용 실제 모델 모드의 hybrid 검색에서 핵심 근거 순서대로 보충하며, vector 모드는 기존처럼 부모 보충을 하지 않습니다. 부모·참조가 부족하면 남는 자리는 검색 후보로 채우고 중복 ID는 한 번만 계산합니다. 명시 조항이 4개보다 많으면 기존 계약에 따라 모두 보존하고 부모·참조 자리를 줄이며, 명시 조항 자체가 7개보다 많을 때는 총 7개 제한의 기존 예외를 유지합니다. 조항 본문의 기존 `ART_MAX` 길이 제한은 바꾸지 않습니다.

검색한 항이 같은 조의 다른 항을 직접 참조하면, 이미 선택한 문단을 제외하고 등록 원문을 최대 1개 추가합니다. 참조 후보가 2개여도 추가 슬롯은 1개이며 기존 참조 함수의 조항 순서로 선택합니다. 예를 들어 제5항이 제1항부터 제4항까지를 가리키면 검색 순위에서 빠진 제1항도 근거 후보가 될 수 있습니다. 절차나 적용 조건의 일부를 확인했다면 답변은 그 내용과 실제 인용 조항을 표시하고, 자료에 없는 세부 조건은 별도로 설명합니다.

| 학습 라벨 | 처리 |
| --- | --- |
| 범위 밖 | 검색과 LLM 호출 없이 `답변 불가`를 표시하고 범위 밖인 이유를 안내 |
| 사내 규정 | 등록된 규정 검색·원문의 적용 대상 전달·근거/숫자 검사·LLM 답변 |
| 사내 생활안내 | DB `knowledge`의 생활 범주 검색·근거/숫자 검사·LLM 답변. 가상 여부와 자료 제약을 출처에 유지 |
| 수자원공사 정보 | DB `knowledge`의 실제 회사 자료를 검색해 답변·출처를 제공. 근거가 부족하면 확인 불가 안내 |

회사 정보는 `knowledge.documents.category=수자원공사 정보`인 실제 자료만 검색해요. 기존 연결 확인 기록은 회사 문서 3종·137개 청크, 가상 생활안내 305개 청크예요. 이번 작업에서 실제 DB 건수를 다시 조회하지 않았어요. 생활 자료는 회사 검색에서 제외하고 생활 범주에서 별도로 검색해요. 후속 질문은 앞 대화를 분류·검색에 사용하고, `meta.classification.usedHistory`로 분류기의 대화 사용 여부를 알려 줘요. 실제 분류 모델의 정확도·검색 품질은 별도 평가가 필요해요.

## 답변 상태와 오류 (2026-11-03 사용자 요청 반영)

1단계에서 RoBERTa가 분류하고, 2단계에서 확신도가 0.80 이상이면 라벨을 그대로 확정합니다. 확신도가 0.80 미만이거나 없으면 선택한 OpenAI 또는 Ollama로 재분류합니다. 4-1·4-2단계의 답변 생성 LLM에는 질문을 다시 분류시키거나 화면의 `answer.kind`를 만들게 하지 않습니다. 서버가 확정한 유형에 따라 자료를 검색하고, 답변 모델은 전달된 자료에서 근거를 골라 답변합니다. RoBERTa 가중치·학습은 이 단계 표기 정리에서 변경하지 않습니다.

사용자 요청에 따라 실제 모델 모드의 되묻기(`clarify`·선택지)는 삭제했습니다. 2026-10-26의 되묻기 확대 기록은 과거 동작이며 현재 요구사항이 아닙니다. 가데이터는 추천 질문의 시연용 예시를 제공합니다.

| 답변 상태 | 규정·회사·사내 생활 표시 | 사내 규정 4-1단계의 의미 |
| --- | --- | --- |
| `refused` | 답변 불가 | 자료 유무보다 먼저 제공 금지 요청으로 판단하여 거절 |
| `not_found` | 근거 확인 불가 | 검색 결과가 비어 있음. 서버의 고정 안내를 사용 |
| `partial` | 근거 확인 | 검색 자료를 인용하여 확인된 내용과 확인하지 못한 부분을 구분. 질문의 답이 없으면 자료의 실제 안내 범위와 한계를 설명 |
| `found` | 근거 확인 | 질문 전체를 자료로 확인하여 인용과 함께 답변 |
| ML 범위 밖 | 답변 불가 | 앞 분류 단계에서 챗봇 범위를 벗어난 질문으로 확정하여 답변 생성 생략 |
| 작업 실패 | 오류 | 모든 질문 유형에 공통인 직원 구분 누락, 연결·시간 초과·응답 검증 실패 등 |

근거 상태는 ML 질문 분류 옆에 표시합니다. `답변 불가`와 `오류`는 각각 단일 결과 라벨로 표시합니다. 시연용 가데이터 표시는 실행 모드를 안내합니다. LLM 근거 상태 라벨은 테스트용이며 배포 시 화면에서 제거할 예정입니다.

`app/agents/grounded_answer.py`에서 규정 4-1단계는 `REGULATION_SYSTEM`, 4-2단계의 수자원공사 정보는 `COMPANY_SYSTEM`, 사내 생활안내는 `LIFE_SYSTEM`으로 프롬프트를 함께 관리합니다. 서버가 확정한 `topic=regulation/company/life`에 따라 해당 프롬프트 하나를 선택합니다. 회사·생활은 공통 근거·출력 지시(`KNOWLEDGE_COMMON_RULES`)를 공유하되, 규정의 적용 대상·별표 판단 지시는 사용하지 않습니다. 회사는 실제 회사 자료의 기준 시점·사업 범위, 생활은 가상 표시·운영 시점·메뉴 안내 범위를 각각 지킵니다. 회사·생활의 세 필드 응답은 유지하며, 검색 자료가 있어도 질문에 답할 수 없으면 `not_found`를 사용할 수 있습니다. `not_found/refused`도 모델이 이유를 `summary`에 작성하며 `sourceIds`만 빈 배열로 유지합니다. 5-2단계는 그 이유를 고정 문구로 교체하지 않습니다.

생활 검색은 `knowledge.documents.category=사내 생활안내`로 한정하고 DB의 원문·문서명·위치·자료 시점·가상 여부·제약을 전달합니다. 실제 인용한 자료만 `knowledgeSources`에 담고 원문 발췌(`excerpt`)와 가상 표시를 화면의 ‘사내 생활 근거 보기’에 제공합니다. DB 자료가 없으면 고정 메뉴로 대체하지 않으며, 가상 식단·시간표·연락처를 실제 운영 정보로 단정하지 않도록 지시합니다. 사실성·검색 품질은 별도 평가가 필요합니다.

연결·시간 초과·JSON 파싱·출처/숫자 검증 실패는 기존 작업 실패 응답을 유지하며 화면에 **오류**로 표시합니다. 검색 실패나 제공 금지 거절로 숨기지 않습니다. 잘못된 인용 ID를 버리고 `근거 확인 불가`로 처리하던 규정 경로도 오류로 구분합니다. 거절 이유는 보호 대상의 종류와 제공 금지 사유만 설명하도록 지시하며, 민감한 원문·개인 식별값·비밀번호·키의 실제 값은 재출력하지 않도록 합니다. 자유 문장의 민감값 여부를 자동 판정하는 검증기를 추가한 것은 아닙니다.

4-1단계는 **제공 금지 → 근거 없음 → 근거 있으나 일부만 확인됨 → 근거 확인** 순서로 판단합니다. 검색을 실행한 뒤 결과가 비어 있어도 LLM에 빈 근거 목록을 전달해 제공 금지 요청인지 먼저 구분합니다. 거절과 빈 검색도 `status`, `summary`, `sourceIds` 세 필드를 모두 반환하며, `refused`는 제공 금지 유형과 이유, `not_found`는 이번 자료에서 확인하지 못한 내용을 요약합니다. 두 상태의 출처는 빈 배열이며 5단계는 그 설명을 그대로 전달합니다. 명시적으로 미등록 조항을 요청한 경우에는 서버가 확인한 조항 안내를 함께 보존합니다. 규정 답변은 자료에서 확인되는 일반 기준과 절차를 안내하며 개인의 승진·보상 결과를 예측하지 않습니다.

규정 검색 자료가 있으면 제공 금지 요청을 제외하고 `partial` 또는 `found`로 요약하며 출처를 최소 하나 선택합니다. 예를 들어 교육 신청 안내만 검색됐는데 지원 금액을 물으면, 신청 안내의 실제 내용과 금액을 확인하지 못한 부분을 두 문장 이내로 설명하고 신청 안내 자료를 인용합니다. 검색됐다는 이유로 질문의 답이 확인된 것처럼 쓰거나, 서버가 임의의 출처를 붙이지 않습니다.

4-1·4-2단계는 Ollama의 `format`에만 `answer_response_schema()`를 전달합니다. OpenAI는 기존 `response_format: {"type":"json_object"}` 호출 방식을 유지하며 출력 스키마를 새로 전달하지 않습니다. [Ollama 공식 문서](https://docs.ollama.com/capabilities/structured-outputs)에 맞춰 최상위 객체에 `status`, `summary`, `sourceIds`를 모두 필수로 지정하고, 다른 속성은 허용하지 않습니다. `answer` 외피는 생성 지시에서 제거했습니다. `status`는 네 값의 열거형이며 출처는 이번 `S001` 같은 별칭으로 제한합니다. `summary`는 `minLength: 1`로 빈 문자열을 금지하며, 공백만 있는 문장도 서버의 `strip()` 검사로 거부합니다. 빈 검색은 빈 출처 배열만 허용합니다. 상태별 인용 개수·규정의 검색 자료 유무 조건은 프롬프트와 서버 검증에서 확인합니다. 추가 재시도나 `evidenceQuote` 필드는 없습니다. OpenAI 응답의 별도 refusal 필드를 refused JSON으로 변환하지 않습니다. LLM이 반환한 JSON의 status만 검증하며, JSON content가 없으면 형식 오류로 남깁니다.

```json
{"status":"found","summary":"신청은 사내 포털에서 해요.","sourceIds":["S001"]}
{"status":"partial","summary":"교육 신청 절차는 확인돼요. 지원 금액은 이번 자료에서 확인되지 않아요.","sourceIds":["S001"]}
{"status":"not_found","summary":"이번 자료에서 통근버스 운영 시간을 확인하지 못했어요.","sourceIds":[]}
{"status":"refused","summary":"타인의 비공개 인사정보 공개 요청이라 제공할 수 없어요.","sourceIds":[]}
```

4-1·4-2단계는 네 상태 모두 세 필드의 타입과 비어 있지 않은 `summary`를 검증합니다. `status`만 있는 예전 응답이나 필드 누락·잘못된 상태값·빈 이유는 자동 보완하지 않고 `4.contract`의 오류로 남깁니다. `refused/not_found`의 이유를 비우거나 고정 안내로 교체하지 않으며, 두 상태에 출처가 들어오면 계약 오류입니다. 실제 출처가 없는 상황에서 ID를 지어내지 않습니다. 없는 ID·빈 인용·규정 자료가 있는데 `not_found`를 반환하는 응답은 검증 오류로 유지하며 임의 인용으로 복구하지 않습니다. 인용·숫자 확인은 근거 존재 검사이며 문장 전체의 의미적 사실성을 보증하지 않습니다.

규정 5-1단계도 `format_regulation_response()` 안에서 **refused → not_found → partial → found** 순서로 처리합니다. 앞 두 상태도 생성된 이유를 표시하며, 명시적으로 요청한 미등록 조항의 안내도 보존합니다. `not_found`인데 검색 ID가 남아 있으면 상태 계약 오류로 처리합니다. `partial/found`는 비어 있지 않은 요약, 이번 검색 목록에 속하고 실제 존재하는 출처, 원문·사용자 조건에 있는 숫자를 검증한 뒤 4-1단계의 요약·인용·상태를 그대로 전달합니다. 질문의 인사 용어와 원문의 단순 문자열 일치 여부로 `not_found`로 바꾸던 처리는 실제 5-1단계에서 제거했습니다. 잘못된 형식·출처·숫자는 검증 오류로 유지하며 추가 LLM 호출은 없습니다.

2026-11-13 사용자 요청으로 네 상태의 JSON 모양을 규정·회사·생활에서 통일했습니다. `REGULATION_*`는 규정, 회사·생활 전용 프롬프트는 각 유형에서 유지하며 공통 출력 지시 `ANSWER_OUTPUT_RULES`와 스키마를 함께 사용합니다. 후속 요청으로 `refused/not_found`도 이유를 비우지 않도록 수정했으며 `sourceIds: []`는 유지합니다. 1단계 분류·2단계 재분류의 `label` 응답, 3단계 검색, 외부 API의 `answer/reg/meta` 구조는 유지합니다. AI가 프롬프트·스키마·검증·5단계 이유 보존과 관련 모의 테스트를 수정했으며, 실제 모델의 지시 준수·인용 품질·응답시간·운영 배포는 별도로 확인해야 합니다.

이유 보존 변경 후 위 9개 테스트 모듈을 같은 읽기 전용·네트워크 차단 컨테이너에서 재검사해 146건 실행·통과했습니다. `found/partial`의 출처 필수, `refused/not_found`의 빈 출처·비어 있지 않은 이유, 공백만 있는 이유 거부, 5단계까지 이유 보존을 확인했습니다. `PYTHONPYCACHEPREFIX=/tmp/pycache python -m py_compile app/agents/grounded_answer.py app/agents/regulation.py app/llm.py tests/test_grounded_answer.py tests/test_question_classifier.py tests/test_regulation_response.py tests/test_assistant_stage_log.py`와 `git diff --check`도 통과했습니다. 현재 `/assistant/ask`의 정상 경로는 LLM의 `status`를 `evidenceStatus`로 그대로 전달하고 계약 오류는 실패로 처리합니다. 기존 화면의 `answerStatus.ts`는 `partial`을 출처 유무에 따라 ‘근거 확인/근거 확인 불가’ 라벨로 표시하지만 실제 `evidenceStatus`를 변경하지 않습니다. 이번 작업에서 해당 표시 규칙은 수정하지 않았습니다.

최종 범위 조정: 사용자 요청에 따라 출력 스키마 전달은 `grounded_answer.generate()`에서 Ollama에만 적용합니다. 로컬에서 추가했던 OpenAI의 `json_schema` 전달과 별도 `refusal` 필드를 `refused` JSON으로 바꾸는 코드는 제거했습니다. OpenAI의 모델 호출 코드는 기존 일반 JSON 방식이며, 모델 JSON에 없는 `status`를 서버가 만들어 넣지 않습니다. 공용 RunPod 주소·키 처리는 GitHub main `bb875d87`의 관련 부분을 반영했고, 필요한 `provider_keys.py`·가용성/설정 확인 함수도 함께 반영했습니다. 관리자 연결 확인은 공용 연결, 직원의 브라우저 임시 연결은 그 브라우저 설정을 사용합니다. `account.py`의 실패 단계·추적 ID 목록과 단계별 상세 조회는 유지합니다. main 전체를 병합한 것은 아니며 충돌한 두 테스트 구간(import 순서·연결 확인용 모의 함수 인자)만 main 기준으로 맞췄습니다.

이 최종 코드에서 `tests.test_runpod_json_integration`, `tests.test_provider_policy`, `tests.test_browser_console`과 위 9개 테스트 모듈을 같은 읽기 전용·네트워크 차단 환경의 `python -m unittest ... -q`로 함께 실행해 168건이 통과했습니다. 공용 주소·키와 Ollama 스키마가 한 HTTP 요청에 함께 들어가는지, 브라우저 키 격리, 설정 복원, 네 상태·이유·출처 검증, 로그 API의 실패 단계·추적 ID·상세 보존을 모의 검사했습니다. 실제 RunPod·OpenAI·운영 사이트는 호출하거나 변경하지 않았습니다.

공통 JSON 계약 변경 후 검증: 기존 `growpath-backend` 이미지에 현재 `backend/`를 `/srv/growpath:ro`로 연결하고 `--network none`, `PYTHONPATH=/srv/growpath`, 가짜 `DATABASE_URL`을 지정한 `python -m unittest tests.test_grounded_answer tests.test_assistant_stage_log tests.test_agent_log tests.test_regulation_response tests.test_regulation_follow_up tests.test_question_classifier tests.test_chatbot_documents tests.test_reasoning tests.test_runtime_json -q`는 145건 실행·통과했습니다. 두 제공자·세 답변 유형·네 상태의 실제 요청 payload, 세 필드 각각의 누락, 잘못된 상태값, 자체 거절 변환, 기존 검색·응답·단계 로그를 모의 검사했습니다. 같은 이미지의 네트워크 차단·읽기 전용 환경에서 `PYTHONPYCACHEPREFIX=/tmp/pycache python -m py_compile app/agents/grounded_answer.py app/llm.py tests/test_grounded_answer.py tests/test_question_classifier.py`와 `git diff --check`도 통과했습니다. 유료 API·RunPod 모델·운영 사이트는 호출하거나 변경하지 않았으며, 사람 리뷰·커밋·푸시·배포는 하지 않았습니다.

2026-11-13 검증(4-2단계 프롬프트 분리 전): AI가 규정 프롬프트·출력 스키마·어댑터·5-1단계 응답 분기와 관련 테스트를 수정했습니다. 관련 개발 이슈는 [#228](https://github.com/20260528-skn-family-ai-33/SKN33-Final-2Team/issues/228)이며, 이 이슈 전체의 완료를 의미하지 않습니다. 기존 `growpath-backend:latest` 이미지에 현재 `backend/`를 `/src:ro`, `database/`를 `/database:ro`, `VERSION`을 `/VERSION:ro`로 연결하고 `--network none --read-only --tmpfs /tmp`, `PYTHONPATH=/src:/src/tests`, 가짜 `DATABASE_URL`, `ROADMAP_TOKENIZER_PATH=/srv/growpath/tokenizer_assets/qwen38.json`으로 아래 검사를 실행했습니다.

- `python -B -m unittest tests.test_regulation_response tests.test_grounded_answer tests.test_question_classifier tests.test_regulation_follow_up tests.test_chatbot_documents -q`: 98건 실행·통과. 5-1단계의 고정 안내 우선, 일부·전체 확인 인용 보존, 상태·빈 요약·미검색/삭제 출처·숫자 검증 실패와 추가 모델 호출 없음을 검사했습니다.
- `python -B -m unittest discover -s tests -q`: 규정 4-1·5-1단계 변경을 포함한 최종 코드에서 대상 1,260건 중 실행·통과 1,251건, 스킵 9건. 별도 복원 DB가 필요한 검사 6건과 외부 실제 카탈로그 스냅샷 검사 3건은 제외됐습니다. 초기 검사에서는 `/VERSION` 연결 누락으로 6건 오류였으며, 파일 연결을 보완한 뒤 오류 없이 통과했습니다. 회사·생활 안내는 OpenAI·Ollama 각각 기존 네 상태 응답과 JSON 모드를 유지하는지 검사했고, `SYSTEM` 원문이 현재 HEAD와 같은 것도 대조했습니다.
- `PYTHONPYCACHEPREFIX=/tmp/pycache python -m py_compile app/agents/grounded_answer.py app/agents/regulation.py app/llm.py tests/test_grounded_answer.py tests/test_question_classifier.py tests/test_reasoning.py`: 통과. 소스에 바이트코드를 쓰지 않았습니다.
- 5-1단계 변경 후 `PYTHONPYCACHEPREFIX=/tmp/pycache python -m py_compile app/agents/regulation.py tests/test_regulation_response.py`: 통과.
- `git diff --check`: 통과. 실제 모델 호출·실제 DB 검색·브라우저 흐름·응답시간·배포는 검증하지 않았습니다. 테스트는 모의 모델을 사용한 계약 검사이며 사람이 직접 테스트하거나 승인한 기록을 대신하지 않습니다. 담당자는 #228의 `golddragon0926`, 검토자는 미정이며 사람 리뷰·커밋·푸시·병합은 남아 있습니다.

2026-11-13 4-2단계 추가 검증: AI가 같은 파일에 회사·생활 전용 프롬프트와 유형별 선택을 추가하고 위 설명 및 관련 테스트를 갱신했습니다. 같은 오프라인 Docker 환경에서 `python -B -m unittest tests.test_grounded_answer tests.test_question_classifier tests.test_regulation_response tests.test_regulation_follow_up tests.test_chatbot_documents -q`로 100건을 실행해 모두 통과했습니다. OpenAI·Ollama별 프롬프트 선택, 기존 네 상태·JSON 모드 유지, 생활 원문의 가상 여부·제약·대화 전달, 잘못된 응답의 오류 전파와 추가 호출 없음을 검사했습니다. 이 결과는 모의 모델을 사용한 계약 검사이며 실제 모델의 지시 준수·검색 품질·브라우저 흐름·배포를 검증한 것은 아닙니다. #228의 사내 정보 응답 보완에 해당하는 로컬 변경이며 이슈 상태·담당·검토·일정은 갱신하지 않았습니다. 사람 리뷰·커밋·푸시·병합은 남아 있습니다.

4-2단계 분리 후 문법 검사도 같은 읽기 전용 Docker에서 `PYTHONPYCACHEPREFIX=/tmp/pycache python -m py_compile app/agents/grounded_answer.py tests/test_grounded_answer.py`로 통과했으며, `git diff --check`도 통과했습니다.

챗봇은 실제 모델과 가데이터 모두 `apply`·`more`·`missing`을 사용하지 않습니다. 확인된 내용과 적용 조건은 `summary`에 담고, 확인하지 못한 부분도 같은 요약에서 설명합니다. 다른 별표·기준을 참조하지만 자료에 없으면 실제 모델 답변은 `partial`을 사용합니다.

규정·회사·사내 생활 프롬프트는 답변 요약을 최대 두 문장으로 작성하도록 지시합니다. 답변 카드 본문에는 요약을 표시하고, 인용한 조항과 문서 출처는 아래 ‘근거 보기’에서 확인할 수 있습니다.

독립 질문에는 과거 질문·근거를 섞지 않습니다. 이어 묻기는 기존 짧은 표현에 더해 ‘그 규정에서 …’, ‘앞에서 설명한 내용을 내 상황에 적용하면 …’, ‘온라인 교육도 교육비 지원을 받을 수 있나요?’처럼 앞 내용을 가리키거나 조건을 보태는 표현을 길이와 관계없이 연결합니다. ‘다른 질문’, ‘새 주제’처럼 주제 변경을 밝히거나 범위 밖 키워드가 있으면 이전 맥락을 분리합니다. 이는 규칙 기반 연결이며 모든 자연어 표현의 의미를 판별하는 모델은 아닙니다.

규정 답변에서 규정 이름 없이 조항 번호를 물으면 이 판별과 별도로 직전 답변의 첫 근거가 속한 규정을 참조합니다. 예를 들어 ‘인재개발규정 제7조 알려줘’ 다음 ‘그 규정 제9조 내용을 알려줘’는 제9조를 자료의 맨 앞과 `requested`에 넣고 이전 질문과 답변도 전달합니다. 미등록 조항이면 규정명·조 번호와 담당 부서에 문의하는 방법을 안내합니다. 명시한 규정 이름은 직전 규정보다 우선하며, 직전 근거가 없거나 삭제됐으면 규정을 추측하지 않습니다. `meta.classification.usedHistory`는 분류기가 앞 대화를 사용했는지만 뜻하므로, 조항 참조 단계에서만 이전 규정을 사용하면 이 값은 거짓일 수 있습니다.

화면은 답변이 끝난 최근 5턴을 보내고 서버는 그중 현재 질문과 이어진 구간을 사용합니다. 각 턴의 질문과 화면에 표시한 답변 본문(`summary`)을 그대로 검색과 답변에 전달합니다. 예전 메뉴형 생활 안내에 본문이 없으면 표시했던 메뉴 정보를 사용합니다. 분류기는 현재 질문을 먼저 읽고 그다음 최신 턴부터 읽습니다. 분류기의 128토큰 입력 한도로 뒤쪽 문맥 일부가 잘릴 수 있습니다.

`kind`·`level` 같은 이전 응답 구조와 `basis`의 실제 출처 ID는 모델 대화에 넘기지 않습니다. 서버는 조항을 찾을 때만 이전 `basis`를 참조합니다. 이번 답변의 출처는 이번에 전달한 자료의 `S001` 같은 별칭으로 검증합니다. 모델은 앞 대화로 후속 질문의 의미를 파악하고 이번 검색 자료를 근거로 답합니다.

Ollama 챗봇 답변에는 `temperature=0`을 보내 생성 변동을 줄이며, 동일 결과를 절대 보장하거나 다른 에이전트의 생성 설정을 바꾸지는 않습니다.

챗봇 파인튜닝 모델(`growpath-regulation-4b` · `qwen35-4b-diagnosis-agent`) 호출에는 `options.num_gpu=-1`을 보내 Ollama 서버가 GPU·VRAM에 맞춰 자동 배치합니다. 지원 GPU가 없으면 CPU를 사용합니다. 진단·로드맵 모델의 장치 옵션과 RoBERTa CPU 분류 설정은 바꾸지 않습니다.

과거 #42 관련 문서에는 LLM 재분류를 제거한 흐름이 기록되어 있습니다. 현재 #138 브랜치의 1~5단계 설명은 2단계의 확신도 기반 재분류를 포함합니다. 변경과 검토 상태는 [PR #238](https://github.com/20260528-skn-family-ai-33/SKN33-Final-2Team/pull/238)에서 확인합니다.

## 회사 정보 근거 연결

현재 DB·모델 설치는 [공유 BGE-M3 DB 연결 (#124)](README.md#공유-bge-m3-db-연결-124)을 따릅니다. 회사·생활은 `knowledge.chunks`, 규정은 `regulations.rag_chunk_embeddings`의 BGE 벡터를 직접 읽으며 강좌·도서도 같은 공식 모델의 질문 임베딩을 사용합니다. CPU 기본은 FP32입니다. 이전 sidecar 테이블은 이 공유본에서 사용하지 않습니다.

`app/knowledge.py`는 기본 BGE-M3 1,024차원 pgvector 검색과 BM25 원문 검색을 RRF로 합쳐 최대 5개를 읽습니다. 벡터 후보에만 코사인 유사도 0.25 기준을 적용하고 BM25는 같은 허용 범주의 전체 원문에서 독립적으로 찾습니다. 원문 해시·실제 자료 필터를 유지하며 사내 생활은 별도 범주에서 가상 자료 여부를 보존합니다. 색인이 없거나 일부 원문과 다르면 오류입니다. 규정도 BM25+BGE-M3의 RRF와 실제 부모 조항 문맥 보충을 사용합니다. 생성 모델은 별도로 선택하며 임베딩의 이전 모델 선택·복구 분기는 제거했습니다. 실제 DB 데이터는 코드 정리에서 삭제하지 않습니다. [공유 DB 검색·복구 안내](README.md#공유-bge-m3-db-연결-124)를 따릅니다.

검색 청크의 앞 3,000자와 문서명·위치·기준 시점·제약을 선택된 답변 모델에 전달합니다. 실제 인용한 결과만 기존 `answer.knowledgeSources`에 담으며, 문서·청크 ID와 원문 위치·시점·해시·잘림 여부를 유지합니다. `basis`는 규정 조항 전용입니다. 회사 답변은 기존 `kind=general`, `source=work`를 유지하고 `topic=company`, `evidenceStatus`를 추가합니다. 이전 대화와 가데이터 응답도 화면에서 계속 읽을 수 있습니다.

AI 사용: Codex가 코드·검사·문서를 수정했습니다. 자동 검사·고정 근거의 로컬 모델 검증은 사람 검토나 RunPod 통합·검색 품질 평가를 대신하지 않습니다. 실행 결과는 최종 작업 보고와 PR 준비 시 확인한 범위만 기록합니다.

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
