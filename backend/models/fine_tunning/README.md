# GrowPath 최종 모델

로드맵 생성용 **Qwen 27B · GrowPath V18 · 최종 2에폭** 모델 안내. 기본 가중치에 LoRA 변경분을 더한 병합 모델이며, Q4_K_M은 별도 양자화 배포본이다.

## 배포 모델

| 구분 | 저장소 | 형식·크기 |
|---|---|---|
| 병합 모델 | [Ssum-mer/qwen3.8-27b-growpath](https://huggingface.co/Ssum-mer/qwen3.8-27b-growpath) | BF16 safetensors · 12샤드 · 가중치 54,713,457,120 bytes(약 54.71 GB) |
| BF16 GGUF | 위 병합 모델 저장소 | 53,808,282,112 bytes(약 53.81 GB) |
| 4비트 GGUF | [Ssum-mer/qwen3.8-27b-growpath-Q4](https://huggingface.co/Ssum-mer/qwen3.8-27b-growpath-Q4) | Q4_K_M · 16,547,400,192 bytes(약 16.55 GB) |

파일 크기는 디스크 저장 용량이며 실행에 필요한 GPU 메모리와 다르다.

## 모델 파라미터

| 항목 | 값 |
|---|---|
| 전체 파라미터 수 | **27,356,728,560개 · 약 27.36B** |
| 저장 정밀도 | BF16 (`bfloat16`) |
| 아키텍처 | `Qwen3_5ForConditionalGeneration` |
| 모델 유형 | `qwen3_5` |
| 텍스트 레이어 수 | 64 |
| Hidden size | 5,120 |
| Attention / KV heads | 24 / 4 |
| 모델 설정의 최대 위치 수 | `max_position_embeddings=262144` |

근거: 공개 저장소의 [config.json](https://huggingface.co/Ssum-mer/qwen3.8-27b-growpath/blob/main/config.json)·[가중치 인덱스](https://huggingface.co/Ssum-mer/qwen3.8-27b-growpath/blob/main/model.safetensors.index.json), 2026-11-04 대조. 저장소 이름의 `qwen3.8`과 실제 config의 `qwen3_5` 표기는 구분한다. 최대 위치 수는 모델 설정값이며 현재 서버의 문맥 할당·실제 처리 성능을 보장하는 값은 아니다.

## 학습 하이퍼파라미터

| 항목 | 값 |
|---|---|
| 최종 에폭 | **2 · 사용자 확인(2026-10-28)** |
| 기본 모델 기록 | `Qwen/Qwen3.8-27B` |
| 기본 revision 기록 | `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0` |
| 학습 데이터 | 원본 1,500건 |
| Learning rate | `0.0001` |
| Batch size | `1` |
| Gradient accumulation | `16` · 기록상 유효 배치 16 |
| LoRA rank / alpha / dropout | `32 / 64 / 0.05` |
| 학습 최대 길이 | `7,168`토큰 |
| Scheduler / warmup ratio | `cosine / 0.05` |
| Weight decay / seed | `0.01 / 42` |

근거: 로컬 보존 `metadata/final_model.json`·`outputs/P01_validity_20261022/execution.json`. 보존 execution은 과거 **1에폭** 기록이며, 위 최종 **2에폭**은 사용자 확정값이다. 이 기록을 최종 2에폭의 전체 실행 로그로 취급하지 않는다. 별도 4B·3,000건 실험 설정과 혼합하지 않는다.

## 현재 프로젝트의 로드맵 생성 설정

| 항목 | 값 |
|---|---|
| 입력 상한 | **11,000** Qwen 기준 토큰 · 시스템 지침·자료 후보·프레이밍 여유 포함 |
| 출력 상한 | **7,000** · OpenAI `max_completion_tokens`, Ollama `num_predict` |
| 기본 문맥 / 로컬 Ollama 설정 | **20,480** |
| 입력 예산 계산의 추가 안전 여유 | **1,024** |

생성·수정의 입력 예산은 `backend/app/catalog_budget.py`, 출력 상한은 `backend/app/llm.py`의 `roadmap` 역할에 적용한다. OpenAI 출력 상한에는 내부 추론 토큰도 포함된다. 명시적으로 더 작은 Ollama 문맥을 사용하면 출력·안전 여유를 먼저 확보하고 입력 예산을 줄인다. 학습 최대 길이와 서비스 문맥 설정은 별개다. 실제 GPU 메모리·지연·출력 품질은 실행 환경별 확인이 필요하다.

## 저장소 포함 범위

위치: `backend/models/fine_tunning/`.

가중치는 Hugging Face에서 내려받아 사용한다. Git에는 이 README와 `.gitignore`만 포함한다. 학습 재현 코드·데이터·설정·평가 원문·과거 보고서·캐시·가중치는 추적에서 제외하며 로컬 파일은 보존한다. 폴더 이동은 모델의 자동 로드·서버 배포 설정 변경을 의미하지 않는다.
