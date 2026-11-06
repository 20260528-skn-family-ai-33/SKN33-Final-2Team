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

## 지켜야 할 것

- 서버 호출은 `src/api/`에만 둬요. 계약이 바뀌면 `docs/API_계약.md`도 함께 고쳐요.
- 화면 문구·CSS를 바꾸면 5차와 달라지는 것이라 따로 검토를 받아요.
- 키·비밀번호는 `.env.local`에만 두고 저장소 파일에 적지 않아요.
