# GrowPath

**업무 목표에서 학습 계획, 실행과 돌아보기까지 이어지는 AI 역량 성장 지원 서비스**

[서비스 접속](https://growpath-edu.site/) · [제품 버전](VERSION) · [설치 및 업데이트](docs/development-setup.md)

GrowPath는 개발·운영 직군 직원이 업무에 필요한 스킬을 고르고, 실제 학습 자료로 개인 로드맵을 만들어 실행하도록 돕습니다. 사내 생활 도우미는 등록된 규정과 회사 자료를 근거로 질문에 답하고, 부서장은 확정된 팀원 계획에 피드백을 남기거나 사후 점검 결과 보고서를 보고 후속 과제를 부여합니다.

[주요 기능](#2-주요-기능) · [AI와 시스템 구조](#4-ai와-시스템-구조) · [AI 에이전트](#5-ai-에이전트) · [산출물](docs/README.md) · [실행 방법](#11-개발-환경-실행)

## 1. 프로젝트 소개

| 항목 | 내용 |
| --- | --- |
| 과정 | SK네트웍스 Family AI 캠프 33기 최종 프로젝트 |
| 팀 | 2팀 **부산별빛샌드** — 송지섭(PM), 신가을(APM), 오호민, 이준희, 김영석 |
| 기간 | 2026.09.28 ~ 2026.11.20 |
| 대상 | 한국수자원공사 공개 자료와 조직을 바탕으로 한 개발·운영 직군 가상 직원 |
| 목적 | 업무 목표를 필요한 스킬과 학습 활동으로 구체화하고, 실행 기록과 사전·사후 점검으로 다음 학습 방향 정하기 |

공개 규정·학습 자료와 가상 직원 데이터를 사용하는 교육 프로젝트입니다. 로그인에는 프로젝트에서 발급한 계정을 사용합니다.

### 역할 분담

| 팀원 | 주요 역할 |
| --- | --- |
| 송지섭(PM) | 직원·로드맵 추천 데이터 고도화, 학습 자료 추천·일정 |
| 신가을(APM) | 프로젝트 기획, 사내 규정 데이터 수집·정제·관리 |
| 오호민 | DB·벡터 검색 초기 설계, 진단·로드맵 에이전트 개발·파인튜닝 |
| 이준희 | React UI 설계·프런트엔드 개발 |
| 김영석 | 사내 생활 도우미 질문 분류, 에이전트 개발·파인튜닝 |

## 2. 주요 기능

| 기능 | 사용자가 할 수 있는 일 |
| --- | --- |
| 목표·스킬 설정 | 업무 목표를 입력하거나 추천 목표를 고르고, 기획서 요약과 본인 프로필을 바탕으로 학습할 스킬을 최대 3개 선택합니다. |
| 사전 역량 테스트 | 스킬별 공통 설문과 프로젝트에 맞춘 퀴즈에 응답하고, 저장된 설문 응답과 퀴즈 정오답·해설을 확인합니다. |
| 3 Course 비교 | Free·Crash·Challenge 계획을 고르고 강좌·도서를 편집합니다. 다른 코스의 자료와 비교하거나 스킬별 산출물 과제를 골라 확정할 수 있습니다. |
| 학습 자료 탐색 | 강좌·도서·자격증을 검색하고 제목순으로 정렬합니다. 강좌는 사이트별로 필터링할 수 있고, 페이지 번호로 원하는 목록에 이동합니다. |
| 학습 실행 | 현재 주차의 활동을 확인하고 진행 상태·메모·선택 첨부를 기록합니다. 같은 로드맵의 동일 강좌는 하나로 묶어 상태를 공유하고 메모·첨부는 활동별로 보존합니다. 도서는 참고 자료로 확인합니다. |
| 사후 점검·보고서 | 사전과 같은 설문, 같은 개념·난이도의 새 퀴즈로 돌아봅니다. 실행 기록과 응답 변화로 보고서가 생성·저장되면 로드맵을 완료하고 본인과 부서장에게 알립니다. |
| 사내 생활 도우미 | 질문을 규정·회사·사내 생활·범위 밖으로 분류하고, 해당 자료와 공개 범위에 맞춰 답변하거나 이용 가능한 메뉴를 안내합니다. |
| 부서장·관리자 | 부서장은 확정 후 진행 중인 소속 직원 계획에 코멘트를 남기고, 결과 보고서에서 별도 후속 과제를 부여합니다. 관리자는 직원·조직·자료·규정과 공용 AI 연결을 관리합니다. |

## 3. 학습 흐름

```mermaid
flowchart LR
    A["목표·스킬 설정<br/>설문·퀴즈"] --> B["3 Course 비교<br/>자료·활동 선택"]
    B --> C["검토·확정"]
    C --> D["학습 실행<br/>진행·메모 기록"]
    D --> E["사후 점검<br/>결과 보고서·후속 과제"]
```

작성 화면은 **목표·기획서 → 세부사항·스킬 선택 → 입력 내용 확인 → 역량 테스트 → 테스트 결과 → 로드맵·자료 선택 → 검토·확정**의 7단계입니다. 로드맵·자료 단계에서는 세 코스 중 하나를 고른 뒤 자료를 편집하고, 필요하면 3열 비교를 엽니다. 검토 단계에서는 이름·기간·시간·비용과 주차별 일정을 확인하고 스킬별 산출물 과제를 비교·선택하거나 과제 없이 확정할 수 있습니다. 새 계획 확정 시 기존 계획과 함께 진행하거나 기존 계획을 사후 점검·보관하는 방식을 선택합니다.

| Course | 작성 관점 |
| --- | --- |
| **Free** | 현재 가격이 확인된 0원 강좌만 사용합니다. |
| **Crash** | 초·중급 강좌 중 목표에 필요한 내용을 짧게 학습하는 구성을 우선합니다. |
| **Challenge** | 중상·상급 강좌 중 실제 업무 적용·실습 근거를 우선하고, 근거가 같으면 상급 강좌를 우선합니다. |

세 Course 모두 사용자가 고정한 선택 스킬을 유지합니다. 교육 예산을 **0원으로 입력하면 모든 코스에서 현재 가격이 확인된 무료 강좌만** 추천·신규 선택할 수 있습니다. 예산 미입력은 0원과 구분하며, 적합한 무료 강좌가 없으면 선택을 비우고 이유를 안내합니다. Crash·Challenge의 기존 계획 수정에서 같은 활동의 동일 강좌를 유지하는 경우는 보존합니다.

도서는 참고·메모용이며 비용·학습 시간·진척률에서 제외합니다. 같은 강좌를 여러 스킬에서 선택해도 시간과 비용은 한 번만 합산하고, 연결된 활동을 모두 마쳐야 완료 강좌로 집계합니다.

스킬 1개를 선택하면 설문 5개·퀴즈 5개, 2~3개를 선택하면 스킬마다 설문 3개·퀴즈 3개에 답합니다. 사후 점검에서는 같은 설문에 다시 답하고 같은 개념을 새 퀴즈로 확인합니다. 설문 점수는 직원의 자기평가입니다.

## 4. AI와 시스템 구조

```mermaid
flowchart TB
    UI["React 사용자 화면<br/>직원 · 부서장 · 관리자"]
    API["FastAPI 업무 서비스<br/>인증·권한·업무 상태<br/>백그라운드 작업"]
    UI -->|"HTTPS · /api/v1 · /api/v2"| API

    subgraph AI["AI 에이전트"]
        direction LR
        subgraph LEARNING["역량 성장 지원"]
            direction TB
            DIAG["진단 에이전트<br/>목표·역량 점검·보고서"]
            ROAD["로드맵 계획 에이전트<br/>3 Course · 자료·과제 제안"]
            DIAG ~~~ ROAD
        end
        subgraph ASSISTANT["사내 도우미 챗봇"]
            direction TB
            CLASSIFIER["ML 질문 4분류<br/>KLUE RoBERTa · CPU"]
            REG["규정 에이전트<br/>유형별 검색·근거 답변"]
            CLASSIFIER -->|"분류 결과"| REG
        end
        LEARNING ~~~ ASSISTANT
    end
    API -->|"생성 요청 · 사내 질문"| AI

    subgraph TOOLS["공통 도구"]
        direction LR
        SEARCH["자료·근거 검색<br/>BGE-M3 · 1,024차원<br/>도우미: BM25 + RRF"]
        RECORD["조회·계산·저장<br/>자료 선택·일정·학습 기록"]
        SEARCH ~~~ RECORD
    end
    MODEL["생성 모델 연동<br/>RunPod-Ollama / OpenAI<br/>Ollama: 학습 27B · 규정 4B"]
    AI -->|"자료 조회 · 정형 처리"| TOOLS
    AI -.->|"문항·계획·답변 생성"| MODEL
    API -->|"일반 조회 · 기록 저장"| TOOLS

    subgraph STORAGE["저장소"]
        direction LR
        DB[("PostgreSQL 17 · pgvector<br/>직원·자료·벡터·계획")]
        FILES[("파일·설정 저장소<br/>규정 원문·첨부·공용 AI 연결")]
        DB ~~~ FILES
    end
    TOOLS -->|"조회 · 검색 · 저장"| STORAGE

    classDef screen fill:#f1f5f9,stroke:#64748b,color:#0f172a
    classDef service fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef learning fill:#eff6ff,stroke:#3b82f6,color:#1e3a8a
    classDef classifier fill:#fff7ed,stroke:#ea580c,color:#7c2d12
    classDef assistant fill:#f0fdfa,stroke:#0d9488,color:#134e4a
    classDef model fill:#f5f3ff,stroke:#8b5cf6,color:#4c1d95
    classDef storage fill:#f8fafc,stroke:#64748b,color:#334155
    class UI screen
    class API,RECORD service
    class DIAG,ROAD learning
    class CLASSIFIER classifier
    class REG,SEARCH assistant
    class MODEL model
    class DB,FILES storage
    style AI fill:#ffffff,stroke:#cbd5e1
    style LEARNING fill:#f8fbff,stroke:#bfdbfe
    style ASSISTANT fill:#f5fffd,stroke:#99f6e4
    style TOOLS fill:#ffffff,stroke:#cbd5e1
    style STORAGE fill:#ffffff,stroke:#cbd5e1
```

FastAPI가 인증·권한·진행 상태를 확인합니다. 진단·로드맵·규정 에이전트는 서버 내부 모듈이며, 생성이 필요한 요청에서 설정된 모델을 호출합니다.

사내 도우미는 KLUE RoBERTa로 질문을 규정·회사 정보·사내 생활·범위 밖으로 분류합니다. 확신도가 **85% 미만이거나 값이 없으면** 선택한 LLM이 한 번 재분류합니다. 사내 자료 검색은 BM25와 BGE-M3의 결과를 RRF로 합치고, 규정에는 같은 부모 조항의 문맥을 보충합니다.

강좌·도서는 목표와 선택 스킬로 BGE-M3 벡터 검색을 수행합니다. 추천 강좌는 코스·예산 조건을 만족해야 하며 이미 이수한 강좌는 제외합니다. 스킬별로 강좌와 도서를 각각 최대 3개까지 제안하고, 사용자가 고른 자료는 확정할 때 다시 검증합니다.

| 구성 | 현재 역할 |
| --- | --- |
| KLUE RoBERTa | 사내 도우미 질문을 4분류하고 결과를 규정 에이전트 챗봇에 전달합니다. 로컬 CPU 추론이며 모델 파일·manifest를 별도로 준비합니다. |
| 팀 파인튜닝 27B · Q4_K_M | 목표·스킬·퀴즈·로드맵·보고서 등 학습 계획 생성. Ollama 이름은 `growpath-27b`이며 모든 역할에서 추론 모드를 끕니다. |
| 팀 파인튜닝 4B · BF16 | 규정·회사 질문 답변. Ollama 이름은 `growpath-regulation-4b`이며 추론 모드는 항상 끕니다. |
| OpenAI 생성 모드 | 관리자 정책에 따라 공용으로 지정하거나 직원이 선택하는 생성 경로입니다. 모델은 서버 설정, 추론 정도는 관리자 또는 허용된 직원 설정을 따릅니다. |
| `BAAI/bge-m3` | 규정·회사 정보·사내 생활·강좌·도서 등 전체 검색용 1,024차원 모델입니다. 공식 고정 revision의 CPU 서버에서 기본 FP32 추론·CLS·FP32 L2 정규화로 질문을 임베딩합니다. |

[분류 모델 연결](backend/classification.md) · [27B 모델 안내](backend/models/fine_tunning/README.md) · [RunPod 연결·27B/4B 모델 준비](backend/RunPod_Ollama_연결_절차.md)

DB는 공유 백업과 동반 manifest를 확인해 복원합니다. 복원한 BGE 벡터를 검색에 사용하며, 생성 모델은 관리자 AI 설정에서 선택합니다. [공유 DB 복원·검색 설정](backend/README.md#공유-bge-m3-db-연결-124)

## 5. AI 에이전트

| 에이전트 | 하는 일 |
| --- | --- |
| 진단 | 직원 프로필에서 목표 후보를 제안하고, 기획서를 요약해 목표에 맞는 스킬을 추천합니다. 공통 설문 풀과 프로젝트별 퀴즈로 점검을 구성하고, 사전·사후 응답과 실행 기록으로 보고서 피드백을 작성합니다. |
| 로드맵 계획 | 같은 목표와 확정 스킬을 바탕으로 Free·Crash·Challenge 세 안을 작성합니다. 검색된 강좌·도서 후보에서 자료를 추천하고 스킬별 실습 과제와 역량 요약을 제안합니다. 선택 자료의 학습 활동과 일정은 서버가 구성·검증하며, 누락된 과제만 한 번 보완 요청합니다. |
| 규정 | 사내 생활 도우미에서 질문을 규정·회사 정보·사내 생활·범위 밖으로 분류하고, 직원군과 공개 범위에 맞는 자료로 답합니다. 근거가 없거나 일부만 확인되면 그 상태를 구분해 안내합니다. 로드맵 3안 생성에서는 교육비 규정 원문을 초안당 한 번 조회하며, 지원 대상과 예산은 교육담당자에게 확인합니다. |

## 6. 데이터와 저장

공개 규정, 외부 강좌·도서·자격 자료, 스킬 매핑, 회사 정보와 가상 사내 생활 안내를 사용합니다. 데모 직원 프로필과 본인 입력은 목표·스킬 추천의 맥락으로 연결합니다.

PostgreSQL은 프로필·초안·확정 계획·버전·자료 선택·활동·점검·보고서·코멘트·후속 과제·알림을 저장하고, pgvector는 자료·규정·회사·사내 생활 검색 벡터를 저장합니다. 별도 GraphDB는 사용하지 않습니다. 관리자 공용 AI 정책과 연결 키는 DB가 아닌 서버 영속 볼륨 파일에 저장하며 조회 응답에 키 원문을 보내지 않습니다.

DB 백업·규정 원문·모델 가중치는 저장소 밖에서 전달합니다. 백업은 **함께 전달된 manifest의 크기·SHA-256**으로 확인합니다. 저장소에 추적된 과거 manifest를 최신 공유본의 해시로 대신 사용하지 않습니다.

[DB 코드와 검사](database/README.md) · [백업·규정 원문 준비](team_db/README.md) · [복원 상세와 이전 이력](database/RESTORE.md)

## 7. 역할과 공개 범위

| 역할 | 공개·수정 범위 |
| --- | --- |
| 직원 | 본인의 입력·초안·계획·활동·점검·보고서를 작성·조회하고, 부서장 후속 과제에 글·파일로 결과를 제출합니다. 본인 비밀번호를 변경할 수 있습니다. |
| 같은 기관·부서의 부서장 | 직원이 **계획 작성을 마치고 확정한 로드맵부터** 조회합니다. 진행 중 계획에는 코멘트를 작성하고, 사후 점검 결과 보고서가 있는 로드맵에는 별도 입력창으로 후속 과제를 부여해 제출 결과를 확인합니다. 마침·보관 계획의 본문은 읽기 전용입니다. |
| 시스템 관리자 | 직원·조직·학습 자료·규정 데이터와 공용 AI 제공자·연결을 관리합니다. 인사평가 입력은 제공하지 않으며, 관리자 데이터 운영 권한과 개인 학습 원본 열람 권한은 구분합니다. |

미확정 초안과 개인 설문·퀴즈 원본, 메모·첨부·평정 등은 부서장에게 공개하지 않습니다. 부서장 코멘트가 확정 계획을 자동 변경하지 않으며, 직원이 수정안을 검토·확정해야 반영됩니다.

보고서는 생성·저장과 함께 확정되며 직원의 별도 확인 버튼을 완료 조건으로 두지 않습니다. 부서장 후속 과제는 계획의 산출물 과제·코멘트와 별개이고, 직원은 글·파일 중 하나 이상으로 한 번 제출합니다. 과제 부여와 제출은 상대방에게 알립니다. 알림함에는 최근 24시간의 읽은 알림도 남기고 읽지 않은 알림을 먼저 표시합니다.

## 8. 기술 스택과 저장소

| 영역 | 구성 |
| --- | --- |
| 화면 | React 19 · TypeScript · Vite · React Router · TanStack Query · Zustand |
| API·서비스 | Python 3.12 · FastAPI · SQLAlchemy · psycopg |
| 데이터·검색 | PostgreSQL 17 · pgvector |
| AI | Transformers · PyTorch CPU · RunPod-Ollama · OpenAI |
| 실행 | Docker Compose · nginx |
| 검사 | Vitest · ESLint · TypeScript · Python unittest · GitHub Actions |

```text
frontend/          사용자·부서장·관리자 화면, API 연결, 비교용 테마
backend/           FastAPI 백엔드, AI 역할, 저장·권한 서비스
└── models/        질문 분류 실행 파일·실험 자료, 27B 모델 안내
database/          DB 코드·마이그레이션·전처리·검색·복원 도구
team_db/           외부 백업·규정 원문을 넣는 위치와 준비 안내
docs/              기획·설계·데이터·모델 산출물과 파일 manifest
scripts/           공유 DB 복원·제품 버전 관리 도구
docker-compose.yml DB·초기 준비·API·화면 실행 구성
```

기본 화면은 다크 모드이며 상단 메뉴에서 라이트 모드와 본문 폭을 선택할 수 있습니다.

## 9. 산출물

[산출물 목록](docs/README.md)에서 요구사항·WBS·기획서·화면설계·수집/전처리·DB/벡터DB·모델·아키텍처 문서를 확인할 수 있습니다. [파일 manifest](docs/artifacts.manifest.json)는 반영 파일의 상대 경로·크기·SHA-256과 원본 링크를 연결합니다.

산출물의 캡처와 실험 수치는 각 문서의 작성 시점을 기준으로 합니다. [팀 산출물 관리 시트](https://docs.google.com/spreadsheets/d/1EQeYN_FpKWzzxHUdtjG9WYaP9t43bvf-H5e1jGMTMEM/edit?gid=1029234216)

## 10. 개발과 검증

프런트엔드는 `frontend/`에서 다음 검사를 실행합니다. [GitHub Actions](.github/workflows/frontend-ci.yml)도 같은 순서로 검사합니다.

```bash
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

백엔드는 `backend/`에서 `python -m unittest discover -s tests -v`를 사용합니다. DB 준비·복원 상태에 따라 필요한 검사가 달라지므로 [백엔드 안내](backend/README.md)와 [DB 검사 안내](database/README.md)를 함께 확인합니다. 화면 흐름·실제 모델 품질·동시 사용자 검증은 단위 검사와 별도로 수행합니다.

일정·WBS는 [팀 Notion](https://app.notion.com/p/ohgiraffers/SKN33_FINAL_2-_-3e9649136c1180f6b847e176dd888c98), 개발 작업은 GitHub Issues, 변경과 검증은 PR에서 관리합니다. 브랜치·커밋 형식 등 협업 규칙은 [AGENTS.md](AGENTS.md)를 따릅니다.

## 11. 개발 환경 실행

[개발 환경 실행 안내](docs/development-setup.md)에 Docker Compose 설치·공유 DB 복원·모델 연결 절차가 있습니다. 기존 설치에서 정식 설정을 적용할 때는 다음 네 값을 `.env`에 반영하고 프런트엔드를 다시 빌드한 뒤 백엔드와 프런트엔드 컨테이너를 재생성합니다.

```dotenv
GP5_DEMO_MODE=off
VITE_DEMO_TOOLS=off
GP5_CONSOLE_OVERRIDES=off
GP5_BETA_ACCOUNT_PICKER=off
```

로그인 화면에서 직접 사번을 입력합니다. `GET /api/v1/console/capabilities`에서 `demo`, `picker`, `browserOverrides`가 모두 `false`인지 확인할 수 있습니다. [기존 설치 업데이트](docs/development-setup.md#기존-설치의-설정-변경과-업데이트)

### 프로젝트 버전과 배포 기록

로그인·상단 메뉴의 버전과 FastAPI의 `/api/openapi.json`은 루트 [VERSION](VERSION)을 사용합니다. 1.0.0부터 후속 수정은 PR 단위로 패치 번호를 올립니다. 변경 이력은 [병합된 PR](https://github.com/20260528-skn-family-ai-33/SKN33-Final-2Team/pulls?q=is%3Apr+is%3Amerged), 버전 갱신 절차는 [에이전트 작업 규칙](AGENTS.md)에 있습니다.
