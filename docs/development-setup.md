# 개발 환경 실행

[프로젝트 README로 돌아가기](../README.md)

Docker Desktop과 Compose v2를 준비합니다. 로컬에서 화면을 개발할 때는 Node.js 20.19 이상(24 권장), Python 직접 실행은 3.12를 사용합니다.

아래 1~4번은 최초 설치 절차입니다. 이미 설치한 환경의 코드·설정을 바꿀 때는 [기존 설치의 설정 변경과 업데이트](#기존-설치의-설정-변경과-업데이트)를 따르세요.

1. 저장소 루트의 `.env.example`을 `.env`로 복사하고 DB용 `GP5_DB_PASSWORD`를 설정합니다. 복원된 직원·관리자는 기존 비밀번호를 사용합니다. 관리자 화면에서 새 직원을 추가할 때만 `GP5_DEMO_PASSWORD`를 별도로 설정합니다.
2. #124의 `growpath_bge_m3_embedding.dump`와 동반 manifest를 `team_db/`에 두고, 아래 명령으로 별도 DB에 복원합니다. 기존 OpenAI DB는 보존합니다. 규정 PDF는 `team_db/regulations/`에 준비합니다.
3. [분류 모델 파일](../backend/classification.md)과 [공식 BGE 가중치](../backend/README.md#공유-bge-m3-db-연결-124)를 준비합니다. 생성에는 기존 RunPod-Ollama 또는 OpenAI 설정을 사용합니다. BGE 검색에는 OpenAI 키가 필요하지 않습니다.
4. 저장소 루트에서 실행합니다(복원 도구는 PowerShell).

```powershell
docker compose up -d --wait db
./scripts/restore-bge-db.ps1 -Apply
docker compose up -d --build --wait --wait-timeout 180
docker compose exec backend python tools/verify_bge_database.py --server
```

| 주소 | 용도 |
| --- | --- |
| <http://localhost:8816> | React 서비스 화면 |
| <http://localhost:8815/api/docs> | FastAPI 문서 |

Compose는 **DB → 복원된 BGE DB 읽기 전용 검사·BGE 서버 준비 → API → 화면** 순서로 실행합니다. 복원은 별도 명령이며 동일 백업 재실행은 건너뜁니다. 공유 DB에는 기존 OpenAI 보충·비밀번호 초기화 도구를 실행하지 않습니다. `docker compose down`은 DB·업로드 볼륨을 보존합니다. 이미 복원한 PC에서 새 공유본으로 바꿀 때는 [새 공유본으로 교체](../team_db/README.md#새-공유본으로-교체) 절차를 따릅니다.

복원한 직원 계정은 **기존 비밀번호**로 로그인합니다. 비밀번호는 백업 제공자·관리자에게 별도로 전달받으세요. 설치기는 직원 비밀번호 해시를 기본으로 보존하며, `GP5_DEMO_PASSWORD`를 설정하거나 설치기를 다시 실행해도 기존 직원 비밀번호를 바꾸지 않습니다. 해시가 NULL이거나 잘못된 형식이어도 임의로 초기화하지 않습니다.

로그인 점검자는 백업 제공자 또는 서비스 관리자에게 시험용 직원 사번과 관리자 아이디, 각 계정의 비밀번호를 비공개로 전달받습니다. 두 계정은 각각 새 브라우저 세션에서 로그인하고, 새로고침 후 같은 역할로 접속되는지와 로그아웃 뒤 `GET /api/v1/me`가 401인지 확인합니다. 로그인 실패 시 계정 종류·아이디·활성 상태부터 확인합니다. 기존 비밀번호를 전달받을 수 없으면 DB 관리 권한자에게 해당 계정만 재설정하도록 요청하고 같은 순서로 재검증합니다. 이슈에는 역할과 검증 결과만 기록합니다.

## BGE 설치기의 계정 보존

`tools/setup_db.py`와 Compose의 `backend-setup`은 복원된 BGE DB를 읽기 전용으로 검사합니다. 관리자 생성·직원 비밀번호 초기화·보충 자료 적재를 자동 실행하지 않습니다. 이전 설치기의 `--reset-team-passwords`, `--keep-team-passwords`, `--supplement-only` 옵션은 DB 검사 전에 오류로 거절합니다. 계정 변경이 필요하면 관리자에게 별도로 요청하고, 이전 설치기를 공유 BGE DB에 실행하지 마세요.

## 설치 환경과 시연 설정

Windows·macOS·Linux 모두 Docker Engine/Desktop과 Compose v2가 필요합니다. macOS·Linux에서는 저장소 루트에서 `cp .env.example .env`로 복사한 뒤 위 1~4번을 진행하세요. Windows에서는 `Copy-Item .env.example .env`를 사용합니다. 기존 `.env`는 덮어쓰지 마세요.

위 복원 스크립트는 PowerShell이 필요합니다. PowerShell을 사용하지 않는 환경은 [공유 DB 수동 복원 안내](../backend/README.md#공유-파일과-복원)를 따릅니다.

관리자 AI 모델 설정에서 OpenAI·RunPod-Ollama를 고정하거나 직원별 선택을 허용할 수 있습니다. 직원별 선택의 초기 모델은 OpenAI입니다. `GP5_EMPLOYEE_AI_SELECTION=off`이면 관리자 고정을 따르며, 고정값이 없으면 RunPod-Ollama를 사용합니다. 검색에는 별도 BGE-M3 모델을 사용합니다.

정식 환경의 기본값은 다음과 같습니다.

| 설정 | 기본값 | 적용 위치 |
| --- | --- | --- |
| `GP5_BETA_ACCOUNT_PICKER` | `off` | 로그인 전 직원 선택기 |
| `GP5_DEMO_MODE` | `off` | 서버 시연 API와 가데이터 |
| `VITE_DEMO_TOOLS` | `off` | 프런트 빌드의 시연 도구 |
| `GP5_CONSOLE_OVERRIDES` | `off` | 테스트 콘솔 단축키와 브라우저별 설정 |

개발 환경에서 콘솔을 사용하려면 서버에 `GP5_CONSOLE_OVERRIDES=on`을 명시하고 백엔드를 재생성합니다. 그러면 `Ctrl+Alt+K`의 `picker on`과 `demo on`이 해당 브라우저에 적용됩니다. 시연 도구를 처음부터 표시하려면 서버와 프런트의 시연 값을 모두 `on`으로 설정합니다. [테스트 콘솔 사용법](../frontend/README.md#브라우저-테스트-콘솔)

### 기존 설치의 설정 변경과 업데이트

기존 `.env`에는 베타 설정이 남아 있을 수 있습니다. 위 네 값을 `off`로 지정하세요. 예전 변수 `GP5_BROWSER_OVERRIDES`도 지원하므로 실행 환경에 남은 `on` 설정을 함께 확인합니다.

신규 요청이 들어오지 않는 점검 시간에 진행 중인 작업이 끝난 것을 확인한 뒤 적용하세요. 현재 백엔드가 실행 중이면 저장소 루트에서 아래 읽기 전용 명령으로 작업 수를 확인할 수 있습니다. 기존 실행에 `-p`나 별도 Compose 파일을 사용했다면 같은 옵션을 사용합니다.

```bash
docker compose exec -T backend python -c "from app import db; print(db.val('SELECT count(*) FROM app_ext.jobs WHERE status = :s', s='running'))"
```

결과가 0이 아니면 작업 완료를 기다린 뒤 다시 확인하세요. 백엔드가 내려가 있다면 DB 연결 도구에서 `SELECT count(*) FROM app_ext.jobs WHERE status = 'running';`을 실행합니다. 조회 뒤 새 작업이 시작되지 않도록 요청 유입도 멈춰야 합니다. 진행 중 작업을 남긴 채 재시작하면 일부 중단 작업이 자동 복구되면서 실제 모델 호출·비용이 발생할 수 있습니다.

**이전 OpenAI DB에서 이번 공유 BGE DB로 처음 전환할 때는 앱만 다시 만드는 아래 명령으로 충분하지 않습니다.** [공유 DB 복원·공식 모델 준비](../backend/README.md#공유-bge-m3-db-연결-124)를 먼저 완료하고, 기존 `.env`에 `GP5_APP_DB_NAME=growpath_bge_m3`, `BGE_M3_MODEL_DIR=./.cache/bge-m3-official-5617a9f`, `BGE_M3_DTYPE=float32`를 반영합니다. 최초 전환은 위 1~4번의 전체 Compose 실행·검증 명령을 사용합니다. 삭제된 이전 임베딩 모델·제공자 선택 설정은 `.env`에서 제거합니다. 이전 DB의 로컬 변경분을 공유 백업으로 자동 이관하지 않으며, 실제 원본 DB와 볼륨은 보존합니다.

이미 공유 BGE DB로 전환한 환경은 선택한 실제 모델의 연결·비용 설정을 확인하고, DB·BGE 서버가 실행 중인 상태에서 앱만 다시 만듭니다. 아래 절차는 DB 스키마·검색 서버 변경이 없는 앱·설정 갱신에 사용합니다.

```bash
docker compose build backend backend-setup frontend
docker compose up -d --no-deps --force-recreate backend frontend
```

`build`는 검사기(`backend-setup`) 이미지도 최신 코드로 갱신하지만 실행하지 않습니다. `up --no-deps`는 API·화면만 다시 만들어 기존 가데이터 결과·직원 선택·비밀번호를 보존합니다. 현재 공유 BGE DB의 `backend-setup`을 다시 실행해도 읽기 전용 검사만 하며 비밀번호를 초기화하지 않습니다. 이전 OpenAI 설치기의 보충·비밀번호 초기화 작업은 공유 BGE DB에 적용하지 않습니다.

모델 연결은 직원의 목표 화면 첫 진입 전에 준비하세요. 저장된 후보가 없고 프로필에 추천 근거가 있는 계정은 첫 진입에서 생성을 시도하며, 모델이 미연결이면 실패 상태가 남을 수 있습니다. 모델을 연결한 뒤에는 목표 후보의 **다시 시도**를 눌러 재생성합니다. 자동 재시도는 하지 않습니다. 기존 가데이터 후보는 삭제되지 않아 계속 가데이터 태그와 함께 보일 수 있습니다.

업데이트 후 `GET /api/openapi.json`의 `info.version`을 로그인 화면과 비교하고, `/api/v1/console/capabilities`의 `picker`, `demo`, `browserOverrides`가 모두 `false`인지 확인합니다.

현재 BGE 설치기는 관리자 계정을 새로 만들지 않으며, 복원된 관리자 계정을 사용합니다. `GP5_ADMIN_PASSWORD`는 남아 있는 관리자 생성 유틸리티의 설정이며 설치 시 자동 적용하지 않습니다. **이미 존재하는 관리자 계정은 자동 갱신하지 않으므로**, 이 설정만 바꾸거나 검사기를 다시 실행해도 기존 비밀번호가 바뀌지 않습니다. 직원은 로그인 후 내 정보에서 현재 비밀번호를 확인해 새 비밀번호로 변경할 수 있고, 변경하면 해당 직원의 모든 로그인 세션을 종료합니다. 관리자 비밀번호 재설정은 배포 담당자가 별도로 처리합니다. 비밀번호는 API·화면·직원 엑셀 안내문으로 배포하지 않으며 관리자가 별도로 전달합니다.

## AI 연결 설정

저장소 루트의 [`.env.example`](../.env.example)을 기준으로 `.env`를 작성합니다. Pod 생성·인증키 설정·두 팀 모델 준비는 [RunPod 연결 절차](../backend/RunPod_Ollama_연결_절차.md)를 따릅니다. 관리자 화면에서는 공용 제공자와 OpenAI 추론 정도, API 키를 관리합니다. 공용 RunPod 주소·키는 연결과 두 모델 설치를 확인한 뒤 함께 저장하며, 확인에 실패하면 기존 연결을 유지합니다. 관리자 등록값이 환경 기본값보다 우선하고 등록을 해제하면 환경 설정으로 돌아갑니다.

| 설정 | 용도 |
| --- | --- |
| `OLLAMA_BASE_URL` · `OLLAMA_API_KEY` | RunPod-Ollama 서버 주소와 인증키의 환경 기본값입니다. 관리자 공용 연결을 저장하면 해당 값이 우선합니다. |
| `OLLAMA_MODEL` · `OLLAMA_MODEL_REGULATION` | 비워 두면 각각 `growpath-27b`(진단·로드맵), `growpath-regulation-4b`(규정)를 사용합니다. Pod에서 준비한 Ollama 모델 이름을 사용합니다. |
| `OLLAMA_THINK` | 더 읽지 않습니다. RunPod-Ollama는 27B·규정 4B의 모든 호출에 `think: false`를 보내 추론 없이 생성하고, 화면에서도 추론 정도를 고르지 않습니다. |
| `OPENAI_API_KEY` | OpenAI 답변 생성용 환경 기본 키입니다. 관리자 등록 키가 우선하며 임베딩에는 쓰지 않습니다. |
| `OPENAI_MODEL` | OpenAI 생성 모드에서 사용할 모델입니다. 서버 설정으로 지정합니다. |
| `GP5_EMPLOYEE_AI_SELECTION` | 직원별 생성 제공자 선택 허용 여부입니다. `off`이면 관리자 공용 정책을 따르며 직원이 제공자를 변경할 수 없습니다. |
| `ASSISTANT_SEARCH_MODE` | 세 범주의 BGE 검색은 기본 `hybrid`(BM25+pgvector+RRF)입니다. `vector`는 기존 벡터 단독 복구용입니다. |
| `GP5_APP_DB_NAME` | 앱과 DB 서비스가 사용하는 공유 BGE DB 이름. 기본 `growpath_bge_m3`입니다. |
| `BGE_M3_MODEL_DIR` | 고정 revision의 공식 가중치·토크나이저 폴더. 기본 `.cache/bge-m3-official-5617a9f`, Git 제외입니다. |
| `BGE_M3_DTYPE` | CPU 추론 기본 `float32`. 메모리를 절약할 때만 `float16`을 명시합니다. 정규화·출력은 FP32입니다. |

## Python 직접 실행

Python 3.12 가상환경을 준비한 뒤 저장소 루트에서 백엔드·DB 도구용 의존성을 설치합니다. Docker로 실행할 때는 이미지 빌드 중 설치됩니다.

```bash
pip install -r requirements.txt
python backend/tools/install_catalog_tokenizer.py
```

토크나이저 준비와 오프라인 설치, 백엔드 직접 실행 방법은 [백엔드 안내](../backend/README.md)를 따릅니다. `backend/`에서 루트의 `.env`를 읽으려면 `GP5_ENV_FILE=../.env`를 지정합니다.

## 화면 직접 실행

화면을 직접 개발할 때는 위 최초 설치 절차로 API·DB를 준비한 뒤 아래 명령을 사용합니다. 이미 설치했다면 [기존 설치의 설정 변경과 업데이트](#기존-설치의-설정-변경과-업데이트)를 따르세요. 개발 화면은 <http://localhost:5185>이며 `/api`는 설정한 백엔드로 전달됩니다.

```bash
npm ci --prefix frontend
npm run dev --prefix frontend
```

[프런트엔드 실행](../frontend/README.md) · [백엔드 실행·설정](../backend/README.md) · [전체 의존성](../requirements.txt)
