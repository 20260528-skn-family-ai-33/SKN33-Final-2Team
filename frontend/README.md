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
| `npm test` | 단위 테스트(Vitest · 계산·주소 변환·관리자 수정 규칙·오류 변환) |
| `npm run build` | 배포용 빌드(`dist/`) |

PR을 올리면 GitHub Actions(`.github/workflows/frontend-ci.yml`)가 같은 순서로 돌려요. 화면 흐름은 테스트가 아니라 브라우저에서 확인해요.

## 지켜야 할 것

- 서버 호출은 `src/api/`에만 둬요. 계약이 바뀌면 `docs/API_계약.md`도 함께 고쳐요.
- 화면 문구·CSS를 바꾸면 5차와 달라지는 것이라 따로 검토를 받아요.
- 키·비밀번호는 `.env.local`에만 두고 저장소 파일에 적지 않아요.
