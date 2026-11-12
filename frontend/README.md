# frontend — GrowPath 화면 (React + Vite + TypeScript)

5차 화면 목업을 모양·문구·CSS 그대로 React로 옮긴 화면이에요.

- 구조와 코드 규칙: [docs/구조_설명.md](docs/구조_설명.md)
- 화면이 백엔드에 기대하는 것: [docs/API_계약.md](docs/API_계약.md)

## 준비물

- Node.js 20.19 이상(24 권장)
- 붙을 백엔드 하나(아래 표)

## 처음 한 번

```bash
npm ci
```

```bash
cp .env.example .env.local
```

Windows PowerShell에서는 `Copy-Item .env.example .env.local`로 복사해요. `.env.local`은 Git에 넣지 않아요.

## 개발 서버

```bash
npm run dev
```

- 주소: <http://localhost:5185> · 코드를 고치면 바로 반영돼요.
- 화면의 `/api` 요청은 `.env.local`의 `API_PROXY_TARGET`으로 넘어가요. 붙을 백엔드에 맞춰 이 한 줄만 바꿔요.

| 붙을 백엔드 | `API_PROXY_TARGET` |
| --- | --- |
| 저장소 맨 위의 `docker compose`(참고용 백엔드) | `http://localhost:8815` |
| 5차 목업 실행본(`목업_실행.cmd`) | `http://localhost:8785` |
| 팀원 백엔드 | 그 서버 주소 |

로그인 계정·시연 비밀번호는 저장소에 없어요. 팀 DB 백업과 함께 담당자에게 받아요.

## 검사

| 명령 | 하는 일 |
| --- | --- |
| `npm run typecheck` | 타입 검사 |
| `npm run lint` | ESLint |
| `npm test` | VERSION 읽기 검사(Node.js)와 단위 테스트(Vitest · 계산·주소 변환·관리자 수정 규칙·오류 변환) |
| `npm run build` | 배포용 빌드(`dist/`) |

PR을 올리면 GitHub Actions(`.github/workflows/frontend-ci.yml`)가 같은 순서로 돌려요. 화면 흐름은 테스트가 아니라 브라우저에서 확인해요.

자료 선택 화면은 로그인한 상태에서 `/new/options`의 **스킬별 자료 비교**에서 확인해요. 백엔드 없이 점검하려면 개발 서버의 [자료 선택 미리보기](http://localhost:5185/docs/material-relevance-preview.html)를 열어요. 두 스킬 탭에서 진단, 자료가 없는 응답의 기존 안내, 저장된 강좌 예시를 확인할 수 있어요. 주소에 `?state=pending` 또는 `?state=error`를 붙이면 기존 준비 중·조회 오류 화면도 확인할 수 있어요. 미리보기는 실제 자료 비교 컴포넌트에 고정 응답을 전달해요.

## 프로젝트 버전

프로젝트 버전은 저장소 루트의 [VERSION](../VERSION)에서만 관리해요. Vite가 시작·빌드 때 읽어 화면에 넣으며, 파일이 없거나 숫자 세 자리 `X.Y.Z` 형식이 아니면 실패해요. 로그인 화면과 직원·부서장·관리자 메뉴 하단에 `GrowPath v버전 · Beta`를 표시해요. `Beta`는 현재 서비스 단계 표시예요. 버전을 바꾼 뒤 개발 서버를 재시작하거나 배포 화면을 다시 빌드해야 해요.

이 프런트 패키지는 배포하지 않는 private 패키지라 별도 `package.json` 버전을 두지 않아요. 화면 숫자는 `VERSION`을 사용해요. 배포 규칙은 [최상위 README](../README.md#프로젝트-버전과-배포-기록)를 따라요.

Docker도 루트 VERSION이 필요하므로 저장소 루트에서 빌드해요(`frontend/`만 따로 복사한 빌드는 지원하지 않아요).

```bash
docker build -f frontend/Dockerfile -t growpath-web .
```

`frontend/Dockerfile.dockerignore`가 VERSION과 프런트 소스만 빌드에 전달하고 `.env`·설치된 패키지·이전 빌드 결과는 제외해요. `docker compose`는 같은 경로를 사용해요.

화면 이미지의 nginx는 JS·CSS 같은 화면 파일을 gzip으로 줄여 보내요(`nginx/default.conf.template`). 1kB보다 작은 파일, 사진, `/api` 응답은 압축하지 않아요. 이미지를 다시 빌드해 화면 컨테이너를 새로 띄우면 적용되고, 아래 명령의 결과에 `gzip`이 나오면 켜진 거예요(주소와 파일 이름은 실행 환경에 맞게 바꿔요).

```bash
curl -s -o /dev/null -H "Accept-Encoding: gzip" -w "%{size_download} %header{content-encoding}\n" http://localhost:8816/assets/<index-해시>.js
```

시연 도구 기본값은 Compose·단독 개발·단독 Docker 빌드 모두 `off`예요(#77). Compose는 루트 `.env`의 `VITE_DEMO_TOOLS`, 단독 개발은 `frontend/.env.local`을 읽어요. 미설정·빈 값·공백·알 수 없는 값은 off이며, 앞뒤 공백과 대소문자를 정리한 `on`만 허용해요. 로컬 시연에는 `VITE_DEMO_TOOLS=on`·`GP5_DEMO_MODE=on`을 함께 명시해요. 단독 Docker 빌드에는 `--build-arg VITE_DEMO_TOOLS=on`도 전달해요. 서버 `/ai/providers`의 `demoMode`가 true일 때만 직원·관리자 시연 도구와 관리자 가데이터 선택지를 표시해요. 기존 설치의 적용·되돌리기는 [최상위 README](../README.md#베타-설치시연-설정-63-64)를 따라요. 직원 고르기는 별도 설정이에요.

### 브라우저 테스트 콘솔

`Ctrl+Alt+K`로 열고 명령을 입력하면 아래에 후보와 설명이 표시됩니다. 방향키로 후보를 고르고 `Tab`으로 자동완성합니다. 예를 들어 `tim`을 입력하고 `Tab`을 누르면 `timeout`과 뒤의 공백이 채워집니다. 원하는 초를 입력한 뒤 `Enter` 또는 `Tab`을 누르면 실행됩니다. 결과에서 `Esc`를 누르면 목록으로 돌아가고, 목록에서 다시 누르면 콘솔이 닫힙니다.

| 명령 예시 | 동작 |
| --- | --- |
| `picker off`, `demo on`, `tools on` | 로그인 직원 고르기, 시연 모드, 시연 도구를 각각 켜거나 끕니다. 서버의 허용 범위 안에서 이 브라우저의 설정이 환경 기본값보다 우선합니다. |
| `runpod url`, `runpod key` | RunPod 연결 설정을 열어 `OLLAMA_BASE_URL`과 `OLLAMA_API_KEY`를 입력합니다. 주소는 RunPod HTTPS 프록시 또는 공개 IPv4와 TCP 포트를 지원합니다. API 키는 가려진 입력란에 넣습니다. |
| `runpod default` | 브라우저의 RunPod 주소와 키만 지우고 서버 기본 연결을 복원합니다. |
| `timeout 180` | 이후 모델 호출 한 번의 대기 한도를 초 단위로 설정합니다(1~900). |
| `inputTokens 8192` | 이후 텍스트 모델 호출의 입력 한도를 설정합니다(1~131072). 프로젝트의 고정 Qwen 토크나이저와 메시지 여유분으로 계산하며 한도를 초과하면 호출 전에 오류를 표시합니다. 이미지를 보내려면 `inputTokens default` 명령으로 복원합니다. |
| `outputTokens 2048` | 이후 모델 호출의 최대 출력 토큰을 설정합니다(1~32768). 실제 생성량은 모델의 컨텍스트와 출력 지원 범위에 따릅니다. |
| `fill` | 설문·퀴즈·사후 진단에서 비어 있는 답만 무작위로 채웁니다. 제출은 화면에서 직접 합니다. |
| `courses`, `courses A2` | 자료 추천 화면에서 해당 코스의 스킬별 최초 모델 입력 강좌(최대 6개)를 입력 순서로 확인합니다. 이전 추천에 후보 기록이 없으면 그 사실을 표시합니다. |
| `status`, `help`, `reset` | 설정·명령을 확인하거나 이 브라우저의 콘솔 설정을 초기화합니다. |

타임아웃과 입출력 토큰 한도는 로그인 전에도 이 브라우저에 저장할 수 있습니다. `status`의 **모델 제한**에서 저장한 값을 확인할 수 있고, 서버가 시연을 허용하고 시연 모드가 켜져 있을 때 모델 호출에 적용됩니다.

RunPod 주소가 비어 있으면 서버 주소를 사용합니다. 주소만 바꾸면 해당 Pod에 인증 없이 연결하므로 키가 필요한 Pod는 함께 입력하세요. 주소와 키는 이 브라우저 프로필의 로컬 저장소에 보관되며 다음 요청부터 적용됩니다.

숫자 대신 `default`를 입력하면 해당 한도만 복원됩니다. 명령 이름은 한 단어로 쓰고 값이나 옵션은 공백으로 구분합니다. 대소문자를 구분하지 않으며 이전 한글 명령도 사용할 수 있습니다. RunPod 연결 설정과 화면 테스트 명령은 서버가 시연을 허용한 직원 세션에서 사용합니다. 설정은 같은 사이트·브라우저 프로필의 로컬 저장소에만 보관하고, 요청 시 적용할 값을 헤더에 전달합니다.

시연 도구의 `기준 날짜`는 로드맵 주차 계산에 쓰는 오늘만 앞으로 옮겨요(`shared/state/demoClock.ts`). 서버 기록은 바꾸지 않고 그 브라우저 탭에서만 적용되며, 실제 오늘보다 이전 날짜는 고를 수 없어요. 시연이 꺼지면 저장된 값도 쓰지 않아요.

## 지켜야 할 것

- 서버 호출은 `src/api/`에만 둬요. 계약이 바뀌면 `docs/API_계약.md`도 함께 고쳐요.
- 화면 문구·CSS를 바꾸면 5차와 달라지는 것이라 따로 검토를 받아요.
- 키·비밀번호는 `.env.local`에만 두고 저장소 파일에 적지 않아요.
