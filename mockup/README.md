# GrowPath 4차 화면 목업

4차 목업의 화면·Python 서버를 팀원이 내려받아 실행할 수 있도록 정리한 폴더입니다. 원본 HTML/CSS/JavaScript와 서버·문서 파서의 동작은 그대로 유지합니다. 별도 프런트 빌드나 Docker는 필요하지 않습니다.

## 최초 설치 (Windows)

Python 3.12에서 실행을 확인했습니다. 아래 명령은 저장소 루트에서 시작합니다.

```powershell
cd mockup
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe check_env.py
.\.venv\Scripts\python.exe server.py --open-browser
```

설치 후에는 `목업_실행.cmd`를 더블클릭하면 실행환경을 확인하고 서버와 브라우저를 엽니다. 기본 주소는 `http://127.0.0.1:8780/`입니다. 종료는 서버 창에서 Ctrl+C입니다. 포트가 사용 중이면 `python server.py --port 8800 --open-browser`로 바꿉니다. 이 문서의 `python`은 설치한 가상환경 Python을 뜻합니다.

Linux/macOS에서는 같은 폴더에서 다음과 같이 실행합니다.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python check_env.py
.venv/bin/python server.py
```

## 시연 방법

- 로그인 화면의 직원 선택에서 가상 직원을 고르고 비밀번호 `0000`을 입력합니다. 예시 직원은 `20200001`, 해당 부서장은 `20070001`입니다.
- 새 로드맵 작성 → 목표·세부 사항 → 사전 점검 → 점검 결과 → 3안 비교 → 검토·확정 순서로 진행합니다.
- 활동 완료 상태·메모를 기록하고 사후 점검·보고서를 볼 수 있습니다.
- 같은 브라우저에서 로그아웃한 뒤 부서장으로 바꾸면 소속 직원의 확정 로드맵을 확인하고 시연 코멘트를 남길 수 있습니다.
- AI 연결 정보가 없으면 가데이터로 동작합니다. 브라우저에 표시되는 가데이터 결과는 실제 모델 추론 결과가 아닙니다.

화면만 보려면 `index.html`을 직접 열어도 됩니다. DOCX/PPTX/HWPX/PDF/HWP 읽기와 실제 AI 연결에는 Python 서버가 필요합니다.

## 선택: 실제 AI 연결

```powershell
Copy-Item .env.example .env
```

`.env`에 사용할 Ollama 주소·모델 또는 OpenAI 키·모델을 입력하고 서버를 재시작합니다. 모델 ID는 사용 중인 제공자에서 확인합니다. `.env` 없이도 가데이터 시연을 할 수 있습니다. 키·주소는 브라우저 코드에 넣지 않으며 `.env`와 `.cache`는 Git에서 제외합니다.

실제 AI 호출에는 비용이 발생할 수 있으므로 팀에서 합의한 계정·예산 범위에서만 연결합니다. 이번 패키지 확인에서는 실제 유료 API를 호출하지 않았습니다.

## 실행환경 확인

`check_env.py`는 Python 버전, 고정 의존성 설치 상태, 필수 목업 파일을 확인합니다. 키 값을 출력하거나 외부 서버에 연결하지 않습니다. 오류가 있으면 1, 준비되면 0으로 종료합니다.

```powershell
python check_env.py
python -m pip check
python -m py_compile server.py docread.py check_env.py tools/mock_ollama.py
```

서버는 Python 표준 라이브러리로 실행됩니다. 추가 의존성은 PDF 읽기용 `pypdf`·이미지용 `Pillow`, 구형 HWP용 `olefile`이며 [`requirements.txt`](requirements.txt)에 버전을 고정했습니다. Node.js는 목업 실행에 필요하지 않습니다.

## 선택: 모의 Ollama 연결

터미널 두 개에서 다음 명령을 각각 실행합니다.

```powershell
python tools/mock_ollama.py --port 11436
python server.py --port 8800 --env tools/mock_ollama.env
```

`http://127.0.0.1:8800/`에서 RunPod-Ollama를 선택합니다. 모의 서버는 고정 응답으로 연결 흐름을 확인하는 도구이며 실제 모델이 아닙니다. 시나리오는 `tools/mock_ollama.py` 상단 설명을 참고합니다.

## 확인 범위와 제한

이 코드는 로컬 화면 시연용입니다. 화면 로그인은 실제 사용자 인증이 아니고, 데이터는 브라우저에 저장돼 다른 기기와 공유되지 않습니다. 서버를 인터넷에 공개하는 운영 배포는 이번 범위에 포함하지 않습니다.

원본의 가상 직원 데이터와 규정 추출 자산을 포함했습니다. 원본 폴더의 `.env`, 캐시, 장문의 변경 이력, 데이터 재생성 도구는 옮기지 않았습니다. 데이터 출처·버전은 각 자산 파일의 메타데이터에 있습니다. 원본 작성자의 검증 이력을 이번 작업의 검증 결과로 재사용하지 않습니다.

작업 이슈: [#8](https://github.com/20260528-skn-family-ai-33/SKN33-Final-2Team/issues/8). 실행 확인 결과와 미검증 항목은 PR에 기록합니다.
