# 챗봇 요청 분류 실험 자료

기존 요청 분류 ML·DL 실험의 코드, 데이터와 저장된 평가 결과를 등록한 폴더다. 서비스에 연결된 추론 API는 포함하지 않는다. 기존 원본 30개의 내용과 줄바꿈은 변경하지 않았다.

## 구성과 입출력

| 파일·폴더 | 입력 → 처리 → 출력 |
|---|---|
| `split_data.py` | `data/original/kwater_4class_questions_2000.csv` → 라벨별 층화 분할 → `data/train.csv`, `data/test.csv` |
| `train_7model_ml.py` | train·test 결합 → TF-IDF와 7종 ML의 5-fold 탐색 → 직렬화 모델, 탐색 CSV, 평가 Excel |
| `train_5model_dl.py` | train·test·val → MLP·CNN·BiLSTM·KLUE RoBERTa·E5 비교 → 모델 파일, 라벨 매핑, 평가 Excel |
| `tune_klue_roberta.py` | train·test·val → RoBERTa 탐색 및 `val_macro_f1` 기준 선택 → 설정·이력·예측·평가지표 |
| `test_dl.py` | 저장된 모델과 `data/new_val.csv` → 추론 → 추가 평가 Excel |
| `data/`, `ML_models/`, `DL_models/` | 원본·분할 데이터, 탐색 기록, 기존 평가 결과 |

## 실행 조건

`split_data.py`와 `train_7model_ml.py`는 현재 작업 경로에 상대적인 파일을 사용한다. 실행할 때 이 폴더를 작업 경로로 둔다. 분할·학습 스크립트는 기존 데이터·결과를 덮어쓸 수 있으므로 재실행 전에 입력과 산출물을 별도 보존해야 한다.

```powershell
cd models/Chatbot_classification
python split_data.py
python train_7model_ml.py
python train_5model_dl.py --help
python tune_klue_roberta.py --help
python test_dl.py --help
```

위 명령은 실행 진입점 안내다. 이번 등록 작업에서는 학습·추론·모델 다운로드를 실행하지 않았다. 실제 실행에는 스크립트에서 사용하는 pandas, NumPy, scikit-learn, joblib, openpyxl, PyTorch, Transformers, sentence-transformers 등의 준비가 필요하다. 이 폴더의 공통 설치 명령과 잠금 파일은 아직 없다.

`DL_models/roberta_tuning_best/run_config.json`에는 해당 실험 당시 Python 3.11.17, PyTorch 2.11.0+cu128, Transformers 5.20.2, scikit-learn 1.9.1, pandas 3.0.6, NumPy 2.4.6이 기록되어 있다. 이는 기존 실행 기록이며 전체 프로젝트의 확정 스택이나 이번 작업에서 재현한 환경을 뜻하지 않는다.

## Git에서 제외한 외부 모델

모델 가중치·직렬화 객체와 사전학습 모델 디렉터리는 Git에 등록하지 않는다. 로컬 파일은 그대로 두고 상대 경로·크기·SHA-256을 [artifacts.manifest.json](artifacts.manifest.json)에 기록했다. 캐시는 해시 목록에서도 제외한다.

외부 보관 위치와 접근 권한은 미정이다. manifest의 `storage_location`이 지정되지 않은 상태에서는 저장소만 내려받아 저장된 모델 평가를 재현할 수 없다. `test_dl.py`는 모델·입력이 없으면 해당 경로를 확인해야 하며, 바이너리 객체는 신뢰할 수 있는 출처에서만 복원해야 한다.

## 평가 결과를 읽을 때

- train 1,600건, test 400건, val 200건이다. 세 분할 사이에 질문 문자열의 완전 일치는 없다. 다만 train/test에 같은 `group_id`가 263개 있어 유사 질문 그룹 누출 여부는 별도 검토가 필요하다.
- ML 코드는 train과 test를 합친 2,000건으로 학습한다. DL·튜닝 코드의 test 사용 방식과 같다고 해석하지 않는다.
- RoBERTa 튜닝은 val 지표로 최적 시행·epoch를 선택한다. 저장된 val 점수는 모델 선택에 사용한 점수이며 독립 최종 평가 결과로 볼 수 없다.
- `new_val.csv`는 ‘범위 밖’ 50건으로만 구성되어 있다. 전체 4개 클래스의 일반화 성능을 나타내지 않는다.
- 데이터 이용 조건·생성 과정·사람 검토 여부, 그룹 기준 분할, 확정 평가셋·외부 모델 보관 위치는 사람 검토가 남아 있다. 이번 등록에서 데이터나 정답은 수정하지 않았다.

형식·해시 검사 결과와 실제 수행 명령은 관련 이슈 #16 및 PR의 검증 기록을 따른다. 기존 성능표의 수치를 이번 작업에서 모델을 실행해 재검증한 것으로 해석하지 않는다.
