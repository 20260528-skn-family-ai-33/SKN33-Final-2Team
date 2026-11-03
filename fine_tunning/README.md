[리커맨드 · 프리 무료강좌 / 크래쉬 단기속성 / 챌린지 하드 트레이닝](docs/RECOMMEND.md)

# fine_tunning

GrowPath 최종 **27B V18 · 2에폭** 모델의 설정·데이터·평가·실행 자료. `SKN33-Final-2Team`에 추가한 독립 파인튜닝 영역. 학습·양자화 결과의 파일 인계와 오프라인 검증 중심 구성.

## 최종 모델

| 항목 | 확정 값 |
|---|---|
| Hugging Face | [Ssum-mer/qwen3.8-27b-growpath](https://huggingface.co/Ssum-mer/qwen3.8-27b-growpath) |
| 고정 revision | `66d1af509ab0681f3b9365227e5c794c65801fbf` |
| 학습 에폭 | **2** · 사용자 확인 |
| 모델 형태 | 기본27B 가중치에 LoRA 변경분 병합 · BF16 · 12샤드 |
| 파라미터·용량 | 27,356,728,560 parameters · 가중치54,713,457,120 bytes |
| 보존 학습 설정 | LR0.0001 · r32/alpha64/dropout0.05 · batch1/누적16 · max7168 · cosine/warmup0.05 · seed42 |
| 학습 입력 | 원본1,500건. 확장3,000건·4B P01~P03은 별도 비교 실험 |
| 평가 | 기존 Gemini3.03/5 / 신규 Codex 직접평가3.42/5 · 평가자별 분리 |

[파라미터 전체와 출처](docs/REPORT.md) · [베이스 비교 수치](docs/REPORT.md). 기존1에폭 execution은 과거 기록으로 보존하며 최종2에폭 전체 로그를 소급 생성하지 않음. 게시 HF의 기본 sampling과 저장 평가의 do_sample=false도 구분.

## 파일 구조

| 경로 | 역할 | 처리 |
|---|---|---|
| `scripts/` | 학습 재현·입력 읽기·원문 검증·패커 | 웹 화면 의존성 없는 CLI 도구 |
| `configs/` | 실험별 설정과 전용 환경 | 설정 파일 존재와 실행 완료 구분 |
| `data/revision_1500/assembled/` | 원본1,500건 | V18 기준 입력·변경 없음 |
| `data/production/expanded_3000/` | 별도4B용3,000건·release·출처·검토17파일 | 원본 앞1,500행 유지 |
| `data/production/curation_1500/` | 과거 분할·출처 기준판 | 전체학습 뒤 독립 평가셋으로 사용 금지 |
| `data/eval/` | 버전별 고정 평가 입력 | 현재·과거 SHA 구분 |
| `reports/` | 실제 입력·base/tuned·manifest | 원 JSON·SHA 보존, 연결 비밀파일 제외 |
| `outputs/` | 소형 학습 결과·해시 영수증 | 대형 어댑터·모델·checkpoint 제외 |
| `docs/` | 현재 모델·평가·실행·변경 이력 | 아래 분류 기준 |

원본 모델 파일은 HF에서 별도 관리. 이 폴더의 존재를 실시간 모델 서버 연결 완료로 보지 않음. 더미 직원 원본·개인 인증 DB·키·캐시·가상환경은 포함하지 않음. `import_manifest.json`은 최초 복사 요약과 정리 후 현재 파일별 SHA를 구분해 기록.

## 문서 분류

| 문서 | 용도 |
|---|---|
| [RECOMMEND.md](docs/RECOMMEND.md) | 프리·크래쉬·챌린지 3안 프롬프트 |
| [REPORT.md](docs/REPORT.md) / [REPORT.html](docs/REPORT.html) | 모델·파라미터·평가·비교·임베딩·이력·연결 절차 통합 |
| [자체 sLLM 인공지능_양식_33기_2팀.docx](docs/자체 sLLM 인공지능_양식_33기_2팀.docx) | 테마를 유지한 검정 글씨 제출 양식 |
| [HISTORY.md](docs/HISTORY.md) | 파인튜닝 시기별 요약 표·변경 이유·글 설명 |
| `metadata/` | 원문 평가 결합·모델·비교 집계·데이터·정리 검증 근거 |

임베딩 설명은 원본 DB 코드 조사 시점의 참고 자료. 새 팀 DB의 현재 행 수·벡터 상태까지 재조회했다고 해석하지 않음. 핵심 문서에 미래 실험 일정을 추가하지 않음.

## 오프라인 확인 환경

저장된 원문·모델 식별·평가 결합 검증은 Python 표준 라이브러리만 사용한다. 학습 데이터 준비 검사에만 PyYAML이 필요하며 GPU 학습 의존성은 별도 파일로 분리한다.

```powershell
$factoryPython = "$env:USERPROFILE/miniforge3/envs/qwen-factory/python.exe"
# fine_tunning 작업 위치
& $factoryPython -S scripts/verify_artifacts.py
& $factoryPython -m pip install -r requirements.txt
& $factoryPython scripts/qwen35_b200_runner.py --phase check
```

입장 암호·Cloud Secrets·웹 앱 실행 설정은 제거했다. 기존 공용 Miniforge 환경 자체를 삭제하거나 패키지를 전역 제거하지 않았다.

## 데이터·평가 재점검

원본1,500건·확장3,000건 JSON 구조·assistant JSON 파싱 오류0, messages 전체 정확 중복0. 3,000건의 앞1,500행 원본 일치. 현재 평가10건 user 원문과 학습 user 원문의 정확 중복0. release 근거17파일 SHA 일치. 각 검토 round의 reviewed_sample_count는30으로 기록. 새 전수 의미·근사 중복·재토큰화 검사를 완료했다고 확대하지 않음.

| 입력 | SHA256 |
|---|---|
| 원본1,500 | `998a9499a14f6c08de0526919567bcf5a9fcf31642f75aa24fca143c51265529` |
| 확장3,000 | `d80e09e8d0283aa1a0276fcef258135d58de89a702664341b244203fefd4e2f2` |
| 현재 평가10 | `7c1565e23373411d1adf5ef50c31ac8842ad68b92fb9c3610440ea1cc411cafe` |

```powershell
# fine_tunning 작업 위치 · 모델/GPU/DB 사용 없는 준비 검사
& $factoryPython scripts/qwen35_b200_runner.py --phase check
# 관련 회귀 검사
& $factoryPython scripts/verify_artifacts.py
```

4B check는 별도3000건 계약 검사이며 최종27B V18의 실시간 추론 테스트가 아님. `DATA_READY_GPU_UNVERIFIED`는 GPU검증 완료가 아님. sample/train/compare의 `--execute` 및 `--resume` 방법은 실행 확인표에 보존한 과거 인터페이스 참고. 종료된 Pod 재연결·재학습 없음.

## 팀 프로젝트 연결

팀 백엔드는 `acts`·catalog의 `res`·기존 활동 `key`를 요구하고 V18은 `milestones`·개별 자료 ID·preserve_paths를 사용. 폴더 추가·모델명 변경만으로 연결 완료 처리하지 않음. [로컬 환경과 상세 연결 절차](docs/REPORT.md)의 입력·출력·자료ID·완료기록 매핑과 endpoint 분리 조건을 우선 확인. 백엔드 참고 사본의 기능·공통 계약은 이번 작업에서 변경하지 않음.

## 전달 ZIP

프로젝트 최상위에서 새 파일명으로 생성. 전체 파일별 SHA256·CRC 확인, 기존 ZIP 덮어쓰기 차단.

```powershell
$factoryPython = "$env:USERPROFILE/miniforge3/envs/qwen-factory/python.exe"
& $factoryPython fine_tunning/scripts/pack_delivery.py --factory-only --output C:/전달경로/fine_tunning.zip
```

Git에는 실행 코드·문서·manifest만 검토해 등록. `data/`, `outputs/`, `reports/`, 비밀 설정·대형 가중치는 제외 규칙 유지. 이번 작업의 커밋·push·PR 없음.


## 전달본 정리

문서는 docs/RECOMMEND.md·docs/REPORT.md로 통합하고 시기별 이력은 docs/HISTORY.md로 분리. REPORT.html은 읽기용, 자체 sLLM 인공지능_양식_33기_2팀.docx는 테마를 유지한 제출 양식. 기계 검증 근거는 metadata/에 분리. 과거 테스트·샘플 제작·원격 점검·유료 평가·메일·중복 패커 Python 제거. 삭제 전 원본은 전달 폴더 외부 작업 백업에 보존.

## 선정 이유

기존 모델보다 약 10% 우위라고 판단해27B V18을 최종 선택. 업무 목적에 맞춘 답변 구성과 병합 모델의 배포·버전 관리 편의를 함께 고려. 선정 판단은 평가자별 측정 점수와 구분.

## 현재 모델 파일 — 2026-10-29

| 형식 | 저장소 | 크기 |
|---|---|---:|
| 병합 Safetensors·BF16 GGUF | [qwen3.8-27b-growpath](https://huggingface.co/Ssum-mer/qwen3.8-27b-growpath) | GGUF 53,808,282,112 bytes |
| Q4_K_M GGUF | [qwen3.8-27b-growpath-Q4](https://huggingface.co/Ssum-mer/qwen3.8-27b-growpath-Q4) | 16,547,400,192 bytes |

두 GGUF의 A100 로딩·짧은 한국어 생성 및 원격 SHA256 확인 완료. 텍스트 생성용이다. 양자화 모델의 전체 품질 평가를 새로 완료한 것은 아니다. 업로드 확인 후 2026-10-29 09:21 KST Pod Stop·EXITED 확인. 모델 가중치는 Git 및 전달 ZIP에 포함하지 않는다.
