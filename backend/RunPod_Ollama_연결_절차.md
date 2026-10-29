# RunPod-Ollama(진단·로드맵 27b · 규정 4b) 연결 절차 · 키 잠금 포함

RunPod Pod를 Terminate한 상태에서 다시 배포하고, nginx로 키를 확인하게 한 뒤, 이 저장소의 참고용 백엔드(`backend/`)에 붙이는 순서예요.

한 Pod에 모델 두 개를 함께 올려 써요(팀 논의 2026-10-29 · #33).

| 에이전트 | 모델 | `.env` |
| --- | --- | --- |
| 진단(목표 후보·기획서 요약·사전 점검·수준 진단·보고서) · 로드맵(3안·수정안) | 팀원이 파인튜닝한 qwen3.8:27b · [Ssum-mer/qwen3.8-27b-growpath-Q4](https://huggingface.co/Ssum-mer/qwen3.8-27b-growpath-Q4) (Q4_K_M · 16.55GB) | `OLLAMA_MODEL` (`OLLAMA_MODEL_ROADMAP`은 비움) |
| 규정(사내 생활 도우미 답변·안별 지원 조건 확인) | 팀원이 파인튜닝한 qwen3.5:4b · [golddragon0926/qwen35-4b-diagnosis-agent](https://huggingface.co/golddragon0926/qwen35-4b-diagnosis-agent) (BF16 · 8.42GB) | `OLLAMA_MODEL_REGULATION` |

- 4b 저장소 이름은 `diagnosis-agent`(진단)이지만 규정 에이전트(사내 생활 도우미)용이에요(2026-10-29 사용자 확인).
- 두 모델 모두 이미지 입력용 vision projector가 없어요(모델 카드). 그래서 기획서 이미지 읽기는 쓰지 않아요(3-2의 `OLLAMA_VISION_MODEL` 비움).

> 작성 2026-10-26 · 두 모델 구성 반영 2026-10-29 · 확인 범위는 맨 아래에 있어요.

```text
GrowPath 백엔드 ──(Bearer 키)──> 공개IP:외부포트 ──> Pod 11434 (nginx: 키 확인) ──> 127.0.0.1:11435 (Ollama, Pod 안에서만)
```

- `<공개IP>`, `<외부포트>`, `<키>`는 실제 값으로 바꿔 넣어요. 공개 저장소라서 실제 값은 이 문서와 저장소에 적지 않아요.
- 이 문서의 모델 이름은 위 표의 팀 모델이에요(2-4 '팀 모델 받기'). 다른 모델을 쓰면 `ollama list`에 보이는 이름으로 바꿔 넣어요. 앱 코드는 고치지 않아도 돼요(이름은 `.env`에서만 읽어요).
- Pod 명령은 RunPod 웹 터미널에서, PC 명령은 저장소 맨 위 폴더에서 실행해요.
- 블록 하나를 통째로 붙여넣고, ✅ 출력을 확인한 뒤 다음 블록으로 넘어가요.
- 웹 터미널에서 Ctrl+V가 안 되면 Ctrl+Shift+V나 마우스 오른쪽 클릭으로 붙여넣어요. 마지막 줄이 실행되지 않고 멈춰 있으면 Enter를 한 번 더 눌러요.

## 1. Pod 배포 (RunPod 화면)

1. Pods → Deploy
2. GPU 기종은 정해 두지 않았어요. 팀 예산과 시간당 요금을 보고 고르되, 두 모델이 문맥용 메모리와 함께 GPU 하나에 다 들어가야 해요.
   - 두 모델 파일만 약 25GB예요(27b Q4_K_M 16.55GB + 4b BF16 8.42GB). 여기에 두 모델 각각의 문맥용 메모리가 더 필요해요.
   - 27b 하나만 쓸 때는 VRAM 40GB 이상을 권장했어요. 지금까지는 48GB GPU에서 원본 qwen3.8:27b 하나만 확인했고, 두 모델이 함께 들어가는지는 아직 확인하지 않았어요(맨 아래 확인 범위). 배포한 뒤 2-5에서 확인해요.
   - 4b는 양자화하지 않은 BF16이에요. 팀원이 Q8_0이나 Q4_K_M으로 양자화해 올리면 약 4~6GB를 줄일 수 있어요.
3. 템플릿은 **Runpod PyTorch**(최신)를 고르고 Edit Template에서 아래처럼 설정해요.

| 항목 | 값 |
| --- | --- |
| Container Disk | 기본값 그대로 |
| Volume Disk | 50GB 이상(두 모델 파일 크기의 합보다 넉넉하게) · Mount Path `/workspace` |
| Expose HTTP Ports | `11434`를 넣지 않음 (같은 포트를 HTTP·TCP 양쪽에 넣을 수 없음) |
| Expose TCP Ports | `22,11434` |
| Environment Variables | 비워 둠 (터미널에서 `export`) |

4. Set Overrides → Deploy On-Demand. 시간당 요금은 이 화면에서 확인하고 팀 예산 안에서 써요.

- ✅ Pod가 Running이 되면 Connect → **Direct TCP Ports**에 `<공개IP>:<외부포트> -> :11434` 줄이 보여요. 적어 둬요.
- ❌ 그 줄이 없으면 TCP 포트에 11434가 빠진 거예요. Terminate하고 다시 배포해요.

## 2. Pod 웹 터미널

Connect → Enable Web Terminal → Open Web Terminal

### 2-1. GPU 확인

```bash
nvidia-smi
```

- ✅ 표에 고른 GPU의 이름과 메모리(`사용량 / 전체`, MiB 단위)가 보여요. 전체 메모리가 1번에서 권장한 VRAM에 맞는지 봐요.
- ❌ `command not found`나 `No devices were found`가 나오면 GPU가 없는 Pod예요. Terminate하고 다시 배포해요.

### 2-2. 설치

```bash
apt update && apt install -y lshw zstd nginx procps openssl && curl -fsSL https://ollama.com/install.sh | sh
ollama -v
nginx -v
```

- ✅ 설치 출력 끝에 `Install complete`나 `NVIDIA GPU installed` 같은 문구가 보여요.
- ✅ `ollama -v`에 `client version is 0.x.y`가 보여요. 앞에 나오는 `could not connect to a running Ollama instance`는 아직 Ollama를 안 켜서 나오는 정상 경고예요.
- ✅ `nginx -v`에 `nginx version: nginx/1.x`가 보여요.
- ➖ `WARNING: systemd is not running`이나 `invoke-rc.d` 관련 문구는 무시해요.
- ❌ `Unable to locate package`가 나오면 이 블록을 다시 실행해요.

### 2-3. Ollama 켜기 (Pod 안에서만 열림)

```bash
mkdir -p /workspace/ollama-models
export OLLAMA_HOST=127.0.0.1:11435
export OLLAMA_MODELS=/workspace/ollama-models
export OLLAMA_NUM_PARALLEL=3
export OLLAMA_MAX_LOADED_MODELS=2
export OLLAMA_KEEP_ALIVE=30m
export OLLAMA_CONTEXT_LENGTH=16384
nohup ollama serve > /workspace/ollama.log 2>&1 &
sleep 5
curl -s http://127.0.0.1:11435/api/version
grep -m1 "inference compute" /workspace/ollama.log
```

- ✅ `{"version":"0.40.11"}` 같은 줄이 나와요.
- ✅ grep 줄에 `library=cuda`와 GPU 이름이 보여요. 문구는 버전에 따라 조금 다를 수 있어요.
- ❌ `Connection refused`가 나오면 몇 초 기다렸다가 curl 줄만 다시 실행해요. 계속 안 되면 `tail -n 30 /workspace/ollama.log`로 오류를 봐요.
- ❌ GPU 줄 대신 `library=cpu`만 보이면 GPU를 못 찾은 거예요. 2-1부터 확인해요.

설정 값의 뜻:

| 값 | 하는 일 |
| --- | --- |
| `OLLAMA_HOST=127.0.0.1:11435` | Ollama를 Pod 안에서만 열어요. 바깥 요청은 2-6의 nginx(11434)가 키를 확인한 뒤 넘겨줘요. |
| `OLLAMA_MODELS=/workspace/ollama-models` | 모델을 볼륨에 둬서 Stop했다 켜도 다시 받지 않게 해요. |
| `OLLAMA_NUM_PARALLEL=3` | 로드맵 3안(A1·A2·A3) 요청 세 개를 차례대로가 아니라 동시에 처리해요. 모델마다 따로 적용돼서 문맥용 메모리도 모델마다 그만큼 잡혀요. |
| `OLLAMA_MAX_LOADED_MODELS=2` | 27b와 4b를 GPU에 함께 올려 둬요. Ollama 기본값(GPU 하나에 3개)으로도 되지만 이 구성을 분명히 하려고 적어요. 메모리가 모자라면 이 값과 관계없이 한 모델을 내려요(2-5에서 확인). |
| `OLLAMA_KEEP_ALIVE=30m` | 요청이 없어도 30분 동안 모델을 GPU에 올려 둬요(기본 5분). 두 모델에 각각 적용돼요. |
| `OLLAMA_CONTEXT_LENGTH=16384` | 앱이 보내는 문맥 길이(`OLLAMA_NUM_CTX`)와 맞춰요. 다르면 앱의 첫 호출 때 모델을 다시 불러와요. 앱은 두 모델에 같은 길이를 보내요. |

⚠️ `export` 값은 이 터미널 창에서만 살아 있어요. 새 창에서 `ollama` 명령을 쓰려면 먼저 `export OLLAMA_HOST=127.0.0.1:11435`를 실행해요.

### 2-4. 모델 받기

모델 두 개(27b·4b)를 받아요. 팀 모델은 아래 '팀 모델 받기'를 그대로 실행해요. 다른 모델을 받을 때는 A(Ollama 라이브러리)나 B(허깅페이스 주소)를 봐요.

#### 팀 모델 받기

```bash
ollama pull hf.co/Ssum-mer/qwen3.8-27b-growpath-Q4
ollama pull hf.co/golddragon0926/qwen35-4b-diagnosis-agent
ollama list
ollama show hf.co/Ssum-mer/qwen3.8-27b-growpath-Q4
ollama show hf.co/golddragon0926/qwen35-4b-diagnosis-agent
```

- 두 저장소 모두 공개 저장소이고 GGUF 파일이 하나씩이라, 양자화 태그(`:Q4_K_M` 등) 없이 받아요. 27b 파일 이름(`qwen3.8-27b-growpath-Q4.gguf`)에는 `Q4_K_M`이 들어 있지 않아서 태그를 붙이면 파일을 못 찾을 수 있어요.
- 4b 저장소에는 학습용 `.safetensors`와 체크포인트도 있지만, Ollama는 GGUF(`qwen35-4b-diagnosis-agent-checkpoint-300-BF16.gguf`)만 받아요.
- ✅ 두 번 모두 진행 막대가 끝나고 `success`가 나와요.
- ✅ `ollama list`에 `hf.co/Ssum-mer/qwen3.8-27b-growpath-Q4:latest`(약 16 GB)와 `hf.co/golddragon0926/qwen35-4b-diagnosis-agent:latest`(약 8 GB)가 보여요. 태그 없이 받아서 `:latest`가 붙어요. 이름이 다르게 보이면 보이는 이름을 그대로 3-2에 써요.
- ✅ 두 모델 모두 `ollama show`의 Capabilities에 `completion`이 있어요. 두 모델 다 vision projector가 없어서 `vision`은 없을 거예요(3-2에서 `OLLAMA_VISION_MODEL`을 비워요).
- 두 모델의 채팅 템플릿은 생각 모드 켜고 끄기를 지원하고, 4b는 생각을 끄고 학습했어요(모델 카드). 3-2에서 `OLLAMA_THINK=off`로 둬요.
- ❌ `connection refused`가 나오면 2-3의 `export`를 하지 않은 창이에요. `export` 줄부터 다시 실행해요.

다른 모델을 받을 때는 아래 둘 중 하나로 받아요.

| 방법 | 언제 쓰나 | `ollama list`에 보이는 이름 |
| --- | --- | --- |
| A. Ollama 라이브러리 | `qwen3.8:27b`처럼 ollama.com에 있는 모델 | `qwen3.8:27b` |
| B. 허깅페이스 주소 | 허깅페이스에 GGUF로 올라와 있는 모델 | `hf.co/<사용자>/<저장소>:<양자화>` |

#### A. Ollama 라이브러리에서 받기

```bash
ollama pull qwen3.8:27b
ollama list
```

- ✅ 진행 막대가 끝나고 `success`가 나와요.
- ✅ `ollama list`에 `qwen3.8:27b`가 약 17~18 GB로 보여요.
- ❌ `connection refused`가 나오면 2-3의 `export`를 하지 않은 창이에요. `export` 줄부터 다시 실행해요.
- ❌ `file does not exist`가 나오면 모델 이름에 오타가 있는 거예요.

#### B. 허깅페이스 주소로 받기 (GGUF)

Ollama는 허깅페이스의 **GGUF 형식** 저장소만 주소로 바로 받아요. 받기 전에 모델 페이지의 Files and versions를 봐요.

- `.gguf` 파일이 있어야 해요. `.safetensors`만 있으면 이 방법으로는 못 받아요. GGUF로 바꿔 올린 저장소를 찾아요.
- 받을 양자화(예: `Q4_K_M`)의 파일 크기를 봐요. 파일 크기에 문맥용 메모리를 더해도 1번에서 고른 GPU의 VRAM에 들어가고, 볼륨에도 자리가 남아야 해요.
- 비공개 저장소면 아래 '비공개 저장소일 때'를 먼저 해요. 공개 저장소면 바로 받아요.

브라우저 주소를 그대로 붙이지 않아요. `https://`를 빼고 `<사용자>/<저장소>`까지만 쓰고, 양자화는 `:` 뒤에 붙여요.

| 브라우저에서 보는 주소 | `ollama pull` 뒤에 쓰는 것 |
| --- | --- |
| `https://huggingface.co/<사용자>/<저장소>` | `hf.co/<사용자>/<저장소>` (`huggingface.co/<사용자>/<저장소>`도 돼요) |
| `https://huggingface.co/<사용자>/<저장소>/blob/main/<파일>.gguf` | `hf.co/<사용자>/<저장소>:<양자화>` 또는 `hf.co/<사용자>/<저장소>:<파일>.gguf` |

모델 페이지의 Use this model → Ollama를 누르면 맞는 명령을 그대로 복사할 수 있어요. 이 메뉴는 허깅페이스 Settings → Local Apps에서 Ollama를 켜야 보여요. 복사한 명령이 `ollama run`이면 `ollama pull`로 바꿔 써도 돼요(`run`은 받은 뒤 대화까지 시작해요).

```bash
ollama pull hf.co/<사용자>/<저장소>:<양자화>
ollama list
ollama show hf.co/<사용자>/<저장소>:<양자화>
```

- `:<양자화>`를 빼면 저장소에 `Q4_K_M`이 있을 때는 그것을, 없으면 저장소 안의 다른 양자화 하나를 골라 받아요. 무엇을 받았는지 분명하게 하려면 적어 줘요.
- ✅ 진행 막대가 끝나고 `success`가 나와요.
- ✅ `ollama list`에 `hf.co/`로 시작하는 이름이 보여요. **이 이름을 그대로 복사해 둬요.** 뒤 단계에서 팀 모델 이름 대신 이 이름을 써요(2-5의 `ollama run`, 3-1의 결과 확인, 3-2의 `OLLAMA_MODEL`·`OLLAMA_MODEL_REGULATION`).
- ✅ `ollama show`의 Capabilities에 `completion`이 있어요. 기획서 이미지 읽기에도 쓰려면 `vision`이 있어야 하고, 생각 모드를 켜려면(`OLLAMA_THINK=on`) `thinking`이 있어야 해요.
- ❌ `The specified tag is not available in the repository`가 나오면 양자화 이름이 저장소의 파일과 맞지 않는 거예요. Files and versions의 파일 이름을 보고 고쳐요.
- ❌ GGUF가 아니라는 오류가 나오거나 여러 조각으로 나뉜 GGUF(`…-00001-of-0000N.gguf`)를 지원하지 않는다는 오류가 나오면, 이 저장소는 이 방법으로 받을 수 없어요. 다른 GGUF 저장소를 찾아요.

**비공개 저장소일 때**

Ollama가 Pod에 만들어 둔 SSH 공개 키를 허깅페이스 계정에 등록해야 받을 수 있어요.

```bash
cat ~/.ollama/id_ed25519.pub
```

- ✅ `ssh-ed25519 AAAA…`로 시작하는 한 줄이 나와요. 공개 키라서 복사해도 돼요. 같은 폴더의 `id_ed25519`(비밀 키)는 열거나 복사하지 않아요.

1. 허깅페이스 Settings → [SSH and GPG Keys](https://huggingface.co/settings/keys) → Add SSH key에 그 줄을 붙여 넣어요.
2. 위의 `ollama pull` 블록을 실행해요.
3. 다 받으면 허깅페이스에서 그 키를 지워요. 키가 등록돼 있는 동안에는 Pod에 들어올 수 있는 사람 누구나 그 계정 권한으로 허깅페이스 저장소에 접근할 수 있어요.

- 키 파일은 볼륨이 아니라 컨테이너 디스크(`~/.ollama`)에 있어요. 그래서 Stop이나 Terminate 뒤에는 새 키가 생겨요. 받은 모델은 `/workspace`에 남으니, 새로 받아야 할 때만 새 키를 등록해요.

### 2-5. 모델 미리 올리기 (선택 · 앱의 첫 호출이 덜 느려짐)

두 모델을 차례로 한 번씩 불러 GPU에 올리고, 둘이 함께 들어가 있는지 봐요.

```bash
ollama run hf.co/Ssum-mer/qwen3.8-27b-growpath-Q4 "한 문장으로 인사해 줘"
ollama run hf.co/golddragon0926/qwen35-4b-diagnosis-agent "한 문장으로 인사해 줘"
ollama ps
```

- ✅ 두 모델 모두 한국어 답이 나와요. 앞에 `Thinking...`이 먼저 보일 수 있어요.
- ✅ `ollama ps`에 **두 줄**이 보이고, 두 줄 모두 PROCESSOR가 `100% GPU`, CONTEXT가 `16384`예요.
- ❌ 한 줄만 보이면(먼저 올린 27b가 사라짐) 두 모델이 GPU 하나에 같이 들어가지 않는 거예요. 이대로 쓰면 진단·로드맵과 도우미를 오갈 때마다 모델을 다시 불러와서 호출이 1분 넘게 걸릴 수 있어요. 더 큰 GPU로 다시 배포해요. `OLLAMA_NUM_PARALLEL`을 줄이면 문맥용 메모리가 줄지만 로드맵 3안을 차례로 처리해서 느려져요.
- ❌ PROCESSOR에 CPU가 섞여 있으면(예: `20%/80% CPU/GPU`) GPU 메모리가 부족한 거예요. 더 큰 GPU로 다시 배포해요.

### 2-6. 키 만들고 nginx 켜기 (다시 실행해도 안전)

```bash
[ -f /workspace/ollama_key.txt ] || openssl rand -hex 32 > /workspace/ollama_key.txt
OLLAMA_KEY=$(cat /workspace/ollama_key.txt)
cat > /workspace/ollama-nginx.conf <<EOF
pid /tmp/ollama-nginx.pid;
events {}
http {
    access_log /workspace/ollama-nginx-access.log;
    error_log /workspace/ollama-nginx-error.log;
    server {
        listen 11434;
        client_max_body_size 50m;
        location / {
            default_type application/json;
            if (\$http_authorization != "Bearer $OLLAMA_KEY") {
                return 401 '{"error":"unauthorized - check OLLAMA_API_KEY"}';
            }
            proxy_pass http://127.0.0.1:11435;
            proxy_set_header Host 127.0.0.1:11435;
            proxy_http_version 1.1;
            proxy_buffering off;
            proxy_read_timeout 600s;
            proxy_send_timeout 600s;
        }
    }
}
EOF
nginx -t -c /workspace/ollama-nginx.conf && { nginx -c /workspace/ollama-nginx.conf -s reload 2>/dev/null || nginx -c /workspace/ollama-nginx.conf; }
```

- ✅ `syntax is ok`와 `test is successful` 두 줄이 나와요.
- ❌ `bind() to 0.0.0.0:11434 failed (98: Address already in use)`가 나오면 다른 프로그램이 11434를 쓰고 있는 거예요(예: 예전 방식으로 켠 Ollama). `pkill -f "ollama serve"`를 실행하고 2-3부터 다시 해요.

이 블록이 하는 일:

- 키 파일(`/workspace/ollama_key.txt`)이 없을 때만 새 키를 만들어요. 있으면 그 키를 그대로 써요.
- nginx 설정을 볼륨에 쓰고, nginx가 켜져 있으면 설정만 다시 읽고(reload), 꺼져 있으면 켜요.
- 참고용 백엔드는 `.env`에 `OLLAMA_API_KEY`가 있으면 요청마다 `Authorization: Bearer <키>`를 붙여 보내요(`backend/app/llm.py`). 그래서 앱 코드는 고치지 않아도 돼요.
- 접근 기록에는 키가 남지 않아요.

### 2-7. Pod 안에서 잠금 확인

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:11434/api/version
curl -s -H "Authorization: Bearer $(cat /workspace/ollama_key.txt)" http://127.0.0.1:11434/api/version
cat /workspace/ollama_key.txt
```

- ✅ 첫 줄은 `401`이에요(키 없이는 막힘).
- ✅ 둘째 줄은 `{"version":"..."}`이에요(키가 있으면 통과).
- ✅ 셋째 줄은 64자리 키예요. 복사해 두되 채팅, 저장소, 공개 채널에는 붙이지 마세요.
- ❌ 둘째 줄에 `502 Bad Gateway`가 보이면 Ollama가 꺼진 거예요. 2-3을 다시 해요.

## 3. PC

### 3-1. 바깥에서 잠금 확인

PowerShell에서는 `curl`이 아니라 `curl.exe`로 써야 해요(Git Bash에서도 그대로 동작해요).

```powershell
curl.exe -i http://<공개IP>:<외부포트>/api/version
```

- ✅ 첫 줄이 `HTTP/1.1 401 Unauthorized`예요.
- ❌ `Failed to connect`나 시간 초과가 나오면 Direct TCP Ports의 IP와 외부 포트, Pod가 Running인지 확인해요.

```powershell
curl.exe -H "Authorization: Bearer <키>" http://<공개IP>:<외부포트>/api/tags
```

- ✅ 결과 JSON에 2-4에서 받은 두 이름(`"name":"hf.co/Ssum-mer/qwen3.8-27b-growpath-Q4:latest"`, `"name":"hf.co/golddragon0926/qwen35-4b-diagnosis-agent:latest"`)이 다 들어 있어요.

### 3-2. `.env` 고치기

저장소 맨 위 `.env`의 Ollama 줄을 이렇게 맞춰요. `.env`가 없으면 [`.env.example`](../.env.example)을 복사해 만들고, 예시에 없는 줄은 더해요(`.env`는 Git에 넣지 않음). 같은 파일의 `OPENAI_API_KEY`도 있어야 해요(규정 검색 임베딩 · 아래 설명).

```text
OLLAMA_BASE_URL=http://<공개IP>:<외부포트>
OLLAMA_MODEL=hf.co/Ssum-mer/qwen3.8-27b-growpath-Q4
OLLAMA_MODEL_ROADMAP=
OLLAMA_MODEL_REGULATION=hf.co/golddragon0926/qwen35-4b-diagnosis-agent
OLLAMA_VISION_MODEL=
OLLAMA_API_KEY=<키>
OLLAMA_TIMEOUT=300
OLLAMA_NUM_CTX=16384
OLLAMA_KEEP_ALIVE=30m
OLLAMA_THINK=off
```

- ✅ 주소가 `https`가 아니라 `http://`로 시작해요(TCP로 직접 붙으면 HTTPS가 없어요).
- ✅ `=` 앞뒤에 공백과 따옴표가 없어요.
- ✅ 같은 이름의 줄이 두 번 들어가 있지 않아요.
- `OLLAMA_MODEL`은 꼭 적어요. 진단 에이전트(목표 후보·기획서 요약·사전 점검·수준 진단·보고서)가 이 모델을 써요. 코드에 기본 모델이 없어서, 비우면 RunPod-Ollama가 '지금 쓸 수 없어요 · .env에 OLLAMA_MODEL이 없어요'로 나와요.
- 백엔드는 `.env`의 이름이 `ollama list`의 이름과 똑같은지로 모델이 있는지 봐요. 태그(`:` 뒤)를 빼고 적으면 `:latest`로 봐요. 그래서 위 예시처럼 `:latest` 없이 적어도 돼요. 2-4 B로 다른 모델을 받았다면 복사해 둔 `hf.co/…` 이름을 그대로 넣어요.
- 모델을 바꿀 때는 이 `.env` 줄만 고치고 3-3을 해요. 앱 코드는 고치지 않아요.
- `OLLAMA_MODEL_ROADMAP`을 비우면 로드맵도 `OLLAMA_MODEL`과 같은 모델(27b)을 써요.
- `OLLAMA_MODEL_REGULATION`은 규정 에이전트(사내 생활 도우미 답변·안별 지원 조건 확인)가 써요. 비우면 `OLLAMA_MODEL`과 같은 모델을 써서, 4b를 받기 전에도 27b 하나로 돌아가요.
- `OLLAMA_VISION_MODEL`은 기획서 이미지 읽기용이에요(선택). 팀 모델은 둘 다 vision이 없어서 비워 둬요. 비우면 이미지 읽기만 안 돼요. 다른 모델을 넣을 때는 `ollama show`의 Capabilities에 `vision`이 있는 모델만 넣어요.
- **규정 검색 임베딩은 두 모드 모두 OpenAI `text-embedding-3-small`이에요**(팀 합의 2026-10-26 · 팀 DB 벡터가 이 모델로 만들어짐). 그래서 Ollama용 임베딩 설정(`OLLAMA_EMBED_MODEL`)은 없어요.
  - RunPod-Ollama 모드만 쓰더라도 `.env`에 `OPENAI_API_KEY`가 있어야 도우미가 규정을 찾아요. 없으면 규정 질문이 '규정 검색 임베딩(text-embedding-3-small)에 쓰는 OpenAI 키가 .env에 없어요'로 실패해요(키워드 검색으로 몰래 바꾸지 않음).
  - 도우미에 한 질문 문장은 임베딩하려고 OpenAI로 가요. 답변은 RunPod-Ollama 모델이 써요.
  - 팀 DB 벡터를 그대로 쓰기 때문에 Pod에 임베딩 모델을 받을 필요가 없어요.
- `OLLAMA_THINK=off`는 생각 모드를 꺼서 생각 없이 바로 답하게 해요(빨라짐). `on`은 켜고, 비우면 모델 기본값(qwen3.8은 켜짐)을 따라요. `on`·`off`가 아닌 값을 적으면 백엔드가 켜지지 않고 멈춰요(`docker compose logs backend`에 이유가 나와요). OpenAI 쪽 추론에는 영향이 없어요. 이 값은 두 모델에 같이 적용돼요(모델마다 따로 정하는 것은 #28). 2-4 B로 받은 두 모델 중 하나라도 Capabilities에 `thinking`이 없으면 `on`으로 두지 않아요. 생각 모드가 없는 모델에 켜라고 보내면 그 모델 호출이 오류가 날 수 있어요.

### 3-3. 백엔드 다시 만들기

compose는 `.env`를 컨테이너를 만들 때만 읽어요. 그래서 백엔드 컨테이너만 새로 만들어요(DB·화면은 그대로).

```powershell
docker compose up -d --no-deps --force-recreate backend
```

- ✅ `Container growpath-backend-1  Started`가 나와요. 이름 앞부분은 `COMPOSE_PROJECT_NAME`에 따라 달라요.
- ❌ compose가 아예 꺼져 있었다면 대신 `docker compose up -d --build`로 전부 켜요.

```powershell
docker compose exec -T backend printenv OLLAMA_BASE_URL OLLAMA_MODEL OLLAMA_MODEL_REGULATION
```

- ✅ 방금 넣은 주소와 두 모델 이름이 나와요. 키는 출력하지 않는 명령이에요.

### 3-4. 화면에서 확인

1. http://localhost:8816 에서 로그인해요(Vite로 개발 중이면 5185). 이미 로그인돼 있으면 새로 고침만 해도 연결을 다시 확인해요.
2. 시연 도구의 '가데이터로 보기'가 꺼져 있는지 봐요.
3. ✅ 좌측 'AI 모델'의 RunPod-Ollama 아래에 `hf.co/Ssum-mer/qwen3.8-27b-growpath-Q4 외 1`이 보이고 `연결됨`이에요. 2-5를 건너뛰었다면 `연결됨 · 모델 준비 중`으로 나오고(자세히 보기에 GPU에 아직 없는 모델 이름이 나와요), 그 모델의 첫 호출이 1분 넘게 걸릴 수 있어요.
4. 작성 흐름을 진행하면서 시연 도구 → '에이전트 동작 보기'에서 호출마다 모델 이름과 걸린 시간을 봐요. 진단·로드맵 에이전트 호출은 27b(`…qwen3.8-27b-growpath-Q4`), 규정 에이전트 호출(사내 생활 도우미 답변·안별 지원 조건 확인)은 4b(`…qwen35-4b-diagnosis-agent`)예요.

### 화면에 오류가 날 때

'자세히 보기(운영자용)'에 나오는 원문 기준이에요.

| 원문 | 원인 | 할 일 |
| --- | --- | --- |
| `Ollama 401: unauthorized - check OLLAMA_API_KEY` (원인 칸: 'Ollama 키(OLLAMA_API_KEY)가 없거나 Pod의 키와 달라요') | `.env`에 키가 없거나 틀림, 또는 3-3을 안 함 | 키를 다시 복사해 넣고 3-3 |
| `Ollama 연결 실패` | IP·포트가 틀림, Pod 꺼짐, nginx 꺼짐 | 3-1부터 확인, 필요하면 Pod에서 2-6 |
| `RunPod 프록시 HTTP 502: Ollama 응답이 아니에요…` | nginx는 켜져 있는데 Ollama가 꺼짐 | Pod에서 2-3 |
| `‘<모델 이름>’ 모델이 Ollama에 없어요` | 모델을 안 받았거나 이름 오타. 2-4 B로 받았다면 `.env`의 이름이 `ollama list`와 한 글자라도 다름. 4b만 없으면 규정 에이전트(도우미 답변·지원 조건 확인)만 실패하고 진단·로드맵은 돼요 | 2-4, 3-2 |
| `Ollama 시간 초과: 300초…` | 동시 요청이 몰렸거나 긴 작업이라 오래 걸림(생각 모드를 켰다면 더 길어짐) | `OLLAMA_TIMEOUT=600`으로 바꾸고 3-3 |
| `규정 검색 임베딩에 필요한 OpenAI 키가 없어요` (도우미 규정 질문) | `.env`에 `OPENAI_API_KEY`가 없음 | 키를 넣고 3-3 |

## 4. 끝낼 때

- **Terminate:** 요금이 완전히 끝나요. 볼륨까지 지워져서 다음엔 1번부터 다시 해요. 모델도 다시 받고, 키도 새로 생기니 `.env`의 키도 바꿔야 해요.
- **Stop:** 볼륨 요금만 나가요. 다시 켤 때는 부록 A를 따라 해요.
- (선택) `.env`의 `OLLAMA_BASE_URL`을 비우고 3-3을 하면, 앱에 RunPod-Ollama가 '지금 쓸 수 없어요'로 나와요.

## 부록 A. Stop 후 다시 Start할 때

컨테이너 디스크가 비워져서 설치와 실행은 다시 해야 해요. `/workspace`에 있는 모델, 키, nginx 설정은 남아 있어요.

순서: 2-2 → 2-3 → (2-5) → 2-6 → 2-7 → Direct TCP Ports에서 새 외부 포트 확인 → 3-1 → 3-2(주소만 바꿈) → 3-3

- 외부 포트는 다시 켤 때마다 바뀌어요. Community Cloud는 IP도 바뀔 수 있어요.
- 2-4는 건너뛰어요. 키도 그대로예요.

## 부록 B. 키 바꾸기 (키가 새어 나갔을 때)

```bash
rm /workspace/ollama_key.txt
```

그다음 2-6 → 2-7을 하고, 새 키를 팀원 모두의 `.env`에 넣은 뒤 각자 3-3을 해요. 옛 키는 바로 401로 막혀요.

## 부록 C. 팀원과 같이 쓸 때

- 주소와 키는 개인 메시지로 보내요. 팀원은 각자 `.env`의 `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`, `OLLAMA_MODEL`, `OLLAMA_MODEL_REGULATION` 네 줄을 넣어요. 도우미 규정 검색에는 각자의 `OPENAI_API_KEY`도 필요해요. 생각 모드를 끄려면 `OLLAMA_THINK=off`도 넣어요. `OLLAMA_MODEL_REGULATION`과 `OLLAMA_THINK`는 참고용 백엔드 `backend/`에만 있는 설정이에요.
- TCP로 직접 붙으면 키가 암호화 없이 전송돼요. 공용 와이파이에서는 조심하고, 실제 개인 정보는 넣지 마세요. 더 안전하게 하려면 Tailscale이나 SSH 터널을 써야 하는데, 팀원마다 설치·설정이 늘어요.
- 누가 두드리는지는 `tail -n 20 /workspace/ollama-nginx-access.log`로 봐요. `401`이 계속 찍히면 누군가 키 없이 접속을 시도하고 있다는 뜻이에요.

## 부록 D. 알아 두면 좋은 것

- **HTTP 프록시 대신 TCP를 쓰는 이유:** RunPod HTTP 프록시(`https://<POD_ID>-11434.proxy.runpod.net`)는 100초 안에 응답이 시작되지 않으면 524로 끊어요. 이 앱 백엔드는 답을 끝까지 기다렸다 한 번에 받고(`stream: false`), `qwen3.8:27b`는 생각 모드가 기본으로 켜져 있어서 로드맵 3안처럼 긴 작업은 100초를 넘기기 쉬워요.
- **모델 두 개:** Ollama는 이름이 다른 모델을 따로 GPU에 올려요. 진단과 로드맵은 같은 27b라 한 번만 올라가고, 규정 에이전트의 4b가 하나 더 올라가요. 앱은 호출마다 `keep_alive`(`.env`의 `OLLAMA_KEEP_ALIVE`)를 보내서, 두 모델 모두 마지막 호출 뒤 그 시간 동안 GPU에 남아요.
- **생각 모드:** `.env`의 `OLLAMA_THINK`로 정해요(3-2). 두 모델에 같이 적용돼요. `off`면 Ollama 요청에 `think: false`를 보내고, 비우면 보내지 않아 모델 기본값(qwen3.8은 켜짐)을 따라요. OpenAI `gpt-6-luna`는 `reasoning_effort`를 보내지 않아 기본값(medium)으로 추론이 켜진 채예요. 두 모드의 결과를 비교할 때는 이 차이를 함께 적어요. 팀원 백엔드에는 아직 이 설정이 없어요.
- **도우미가 '확인 불가'라고 할 때:** 먼저 검색이 조항을 찾았는지 봐요. 2026-10-26 전에는 RunPod-Ollama 모드가 키워드 검색을 해서, "근로 시작일은 한 달 기준 며칠 부터야?" 같은 질문은 조항을 0개 찾았어요(OpenAI 모드는 벡터 검색으로 「연봉규정」 제4조를 찾음). 지금은 두 모드가 같은 벡터 검색을 해요. 또 같은 날 지시문(`REG_SYS`)을 고쳐서, 뜻이 여러 가지로 읽히는 규정 질문은 '확인 필요'로 되묻고 선택지 버튼을 보여 줘요. 고르면 그 뜻으로 조항을 찾아 답해요. 고치기 전에는 qwen3.8이 같은 질문에 한 번은 '확인 불가', 한 번은 되묻기로 답했어요.
- **CPU 100%:** 모델이 GPU에 다 올라가 있어도 토큰마다 다음 토큰 고르기와 JSON 형식 검사(`format: json`)는 CPU가 해요. 요청 여러 개를 동시에 처리하면 RunPod 화면의 CPU가 100%까지 차는데, 고장은 아니에요. GPU를 바꿔도 CPU 표시는 비슷하고, 빨라지는 건 답 만드는 속도예요.

## 확인 범위 (2026-10-26)

아래 Pod 확인은 모두 A40(48GB) 한 종류로 했어요. 확인할 때 쓴 GPU일 뿐, 팀이 쓸 GPU로 정한 것은 아니에요.

- **2-6·2-7(nginx 키 확인):** PC의 nginx 1.28 Docker 컨테이너와 가짜 Ollama로 네 가지 경우를 확인했어요.
  - 처음 켜기
  - 다시 실행(같은 키 유지)
  - 키 바꾸기(옛 키는 401)
  - Stop 뒤처럼 처음부터 다시 켜기

  키 없음은 401, 맞는 키는 통과했고, 접근 기록에 키가 남지 않았어요.
- **2-1~2-5와 3번:** 확인용 A40 Pod에서 **키 없는 버전**(Ollama를 `0.0.0.0:11434`로 직접 연 구성)으로 실제 연결과 호출, 앱 화면의 '연결됨'까지 확인했어요(Ollama 0.40.11). 첫 호출은 모델을 GPU에 올리느라 약 83초(불러오기 42초), 그다음 짧은 호출은 약 4초 걸렸어요.
- **`OLLAMA_THINK`:** 백엔드 컨테이너에서 `off`면 `think: false`, `on`이면 `think: true`를 보내고, 비우면 보내지 않는 것을 확인했어요. 틀린 값(`false` 등)은 시작할 때 멈춰요. 끄는 효과는 Pod를 종료하기 전에 같은 짧은 질문으로 따로 재 봤어요(생각 켬 3.7초 · 끔 1.8초). 앱 흐름 전체(3안 등)에서 얼마나 빨라지는지는 재지 않았어요.
- **새로 고침 뒤 연결 확인:** 로그인한 채 새로 고치면 연결 확인 요청이 한 번 나가고, '연결 확인 중…'에서 결과(연결됨 / 연결 안 됨)로 바뀌는 것을 화면에서 확인했어요(Pod가 꺼진 상태라 '연결 안 됨 · Connection refused'로 확인).
- **실제 Pod에서 키 잠금까지 (2026-10-26):** 담당자가 이 절차로 새로 띄운 확인용 A40 Pod(RunPod PyTorch 이미지 · nginx 설치 포함)로 확인했어요.
  - 키 없음·틀린 키 → 401로 막히고, 화면에 '연결 안 됨 · Ollama 키(OLLAMA_API_KEY)가 없거나 Pod의 키와 달라요'가 떠요.
  - `.env`에 키를 넣고 3-3 → 연결 확인 성공(Ollama 0.40.11), 화면 '연결됨'.
  - 생각을 끈 짧은 호출이 1.9초 걸렸고, 2-5로 미리 올린 모델을 다시 불러오지 않았어요(불러오기 2ms · `OLLAMA_CONTEXT_LENGTH`와 `OLLAMA_NUM_CTX`가 같아서).
- **아직 안 한 것:** 키 잠금 구성에서 앱 흐름 전체(사전 점검 → 3안)를 돌려 걸린 시간을 재지는 않았어요.
- **허깅페이스 주소로 받기(2-4 B · 2026-10-28 추가):** 실제 Pod에서는 해 보지 않았어요. 받는 명령, 기본 양자화, 비공개 저장소 키 등록은 허깅페이스 공식 안내를 따랐어요. `.env` 이름 맞추기는 백엔드 연결 확인 코드(`backend/app/llm.py`)를 보고 썼어요. 나뉜 GGUF 오류는 공식 안내가 아니라 사용자 이슈 보고를 근거로 했어요.
- **두 모델 구성(#33 · 2026-10-29 추가):** 실제 Pod가 아니라 격리 Docker 스택과 모의 Ollama(`backend/tools/mock_ollama.py` · 진단 모델 대신 `qwen3.5:9b`, 규정 모델 대신 `growpath-regulation:4b`)로만 확인했어요. OpenAI 키는 비워 유료 호출을 하지 않았어요.
  - 규정 에이전트(도우미 답변·안별 지원 조건 확인)는 규정 모델로, 진단·로드맵(3안)은 `OLLAMA_MODEL`로 호출되고 '에이전트 동작 보기' 기록에도 그 이름이 남아요.
  - 연결 확인이 두 모델을 함께 봐요. 규정 모델만 GPU에 없으면 '연결됨 · 모델 준비 중', 규정 모델만 없으면 '연결 안 됨 · ‘<모델 이름>’ 모델이 Ollama에 없어요'이고, 그때도 진단·로드맵 호출은 돼요.
  - `OLLAMA_MODEL_REGULATION`을 비우면 규정 에이전트도 `OLLAMA_MODEL`을 써요.
  - 도우미 답변이 모의 규정 모델까지 가는 것은 규정 검색을 키워드 검색으로 바꾼 확인 스크립트로 봤어요. 화면에서는 키가 없어 임베딩 단계에서 멈췄고, 기록의 모델 이름만 확인했어요.
  - **팀 모델 저장소:** 허깅페이스 API와 모델 카드에서 공개 여부, GGUF 파일 수·이름·정밀도·크기, vision projector 미포함, 채팅 템플릿의 생각 모드 지원만 확인했어요. 받는 명령(태그 없이)과 `ollama list`의 `:latest` 이름은 이 정보로 정한 거라 실제로 받아 본 결과가 아니에요.
  - **아직 안 한 것:** 두 모델을 실제 Pod에 받아 함께 올리기(2-4·2-5), 그 GPU에 둘 다 들어가는지, `ollama show`의 Capabilities, 두 모델이 앱 지시문의 JSON 형식(규정 에이전트는 `REG_SYS`·`SUP_SYS`)을 따르는지. 4b 모델 카드의 확인 예시는 JSON이 아니라 "…출처: [S001]" 같은 문장이라, 형식 오류나 근거 누락이 나는지 Pod에서 앱 흐름으로 봐야 해요.
- 설치 완료 문구 같은 출력 예시는 버전에 따라 조금 다를 수 있어요.

참고: [RunPod – Run Ollama on a Pod](https://docs.runpod.io/tutorials/pods/run-ollama) · [RunPod – Expose ports](https://docs.runpod.io/pods/configuration/expose-ports) · [RunPod 프록시 안내](https://www.runpod.io/blog/runpod-proxy-guide) · [Ollama – qwen3.8:27b](https://ollama.com/library/qwen3.8:27b) · [Ollama FAQ – 여러 모델 함께 올리기](https://docs.ollama.com/faq) · [Hugging Face – Use Ollama with any GGUF Model](https://huggingface.co/docs/hub/en/ollama)
