"""
========================================================================================
[실험 대상 7종 전통 머신러닝(ML) 텍스트 분류 모델]

1. Logistic Regression (로지스틱 회귀)
   - TF-IDF 고차원 희소 행렬 분류의 표준 선형 모델.
   - 단어별 가중치를 선형 결합하고 시그모이드/소프트맥스 함수를 거쳐 클래스 확률을 예측.

2. Linear SVC (선형 서포트 벡터 분류기)
   - 클래스 간 마진(Margin)을 최대화하는 선형 초평면을 학습하는 SVM 모델.
   - 대규모 텍스트 분류 작업에서 빠르고 강력한 일반화 성능을 제공.

3. Kernel SVM (비선형 커널 서포트 벡터 분류기)
   - RBF(가우시안) 및 선형 커널을 적용하여 비선형 결정 경계를 형성하는 SVM.
   - 데이터 간 복잡한 비선형 관계를 포착할 수 있으나 연산 비용이 상대적으로 큼.

4. Complement Naive Bayes (보완 나이브 베이즈)
   - 텍스트 분류에 특화된 확률 기반 나이브 베이즈 알고리즘.
   - 클래스 불균형(Imbalanced Data) 상황에서 일반 다항 나이브 베이즈보다 견고함.

5. SGD Classifier (확률적 경사 하강법 기반 선형 분류기)
   - Mini-batch/샘플 단위의 경사 하강법으로 목적함수(Log Loss 등)를 최적화.
   - 대규모 희소 텍스트 데이터셋에서도 매우 빠른 학습 속도를 지원.

6. Random Forest (랜덤 포레스트)
   - 수많은 의사결정나무(Decision Tree)를 배깅(Bagging) 기법으로 결합한 앙상블.
   - 다양한 서브샘플과 특성 조합으로 과적합을 방지하고 안정적인 예측을 제공.

7. Extra Trees (극단적 랜덤 트리)
   - 랜덤 포레스트와 유사하나 분할 지점(Split point)을 무작위로 선택하는 앙상블.
   - 트리의 무작위성을 극대화하여 분산(Variance)을 줄이고 연산 속도를 개선.
========================================================================================
"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.metrics import accuracy_score, f1_score

# 7종 대표 모델
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.svm import LinearSVC, SVC
from sklearn.naive_bayes import ComplementNB
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier

# 1. 경로 설정 및 데이터셋(Train+Test 통합, Val) 준비
DATA_DIR = "data"
MODEL_DIR = "ML_models"
TUNING_DIR = os.path.join(MODEL_DIR, "tuning_details")
OUTPUT_DIR = os.path.join(MODEL_DIR, "excel_reports")
os.makedirs(TUNING_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# train.csv와 test.csv를 병합하여 ml_train.csv로 생성 및 로드
train_path = os.path.join(DATA_DIR, "train.csv")
test_path = os.path.join(DATA_DIR, "test.csv")
ml_train_path = os.path.join(DATA_DIR, "ml_train.csv")

train_df = pd.read_csv(train_path).fillna({"question": ""})
test_df = pd.read_csv(test_path).fillna({"question": ""})

# 두 데이터를 합쳐 ml_train.csv 파일로 보관
ml_train_df = pd.concat([train_df, test_df], ignore_index=True)
ml_train_df.to_csv(ml_train_path, index=False, encoding="utf-8-sig")
print(f"[*] ML 통합 학습 데이터 생성 완료 -> {ml_train_path} (총 {len(ml_train_df)}건)")

# 최종 독립 평가용 데이터셋 (val.csv)
val_dict = {
    "val": pd.read_csv(os.path.join(DATA_DIR, "val.csv")).fillna({"question": ""}),
}

X_train_full = ml_train_df["question"]
y_train_full = ml_train_df["label"]

# 라벨 비율을 보존하는 Stratified 5-Fold 정의
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

# 2. 7종 모델별 파라미터 탐색 그리드 정의
model_experiments = {
    "Logistic_Regression": {
        "pipeline": Pipeline([
            ("tfidf", TfidfVectorizer(sublinear_tf=True)),
            ("clf", LogisticRegression(max_iter=1000, random_state=42))
        ]),
        "params": {
            "tfidf__ngram_range": [(1, 1), (1, 2)],
            "clf__C": [0.1, 0.5, 1.0, 5.0, 10.0],
            "clf__class_weight": ["balanced", None]
        }
    },
    "Linear_SVC": {
        "pipeline": Pipeline([
            ("tfidf", TfidfVectorizer(sublinear_tf=True)),
            ("clf", LinearSVC(dual="auto", random_state=42))
        ]),
        "params": {
            "tfidf__ngram_range": [(1, 1), (1, 2)],
            "clf__C": [0.1, 0.5, 1.0, 2.0, 5.0],
            "clf__class_weight": ["balanced", None]
        }
    },
    "Kernel_SVM": {
        "pipeline": Pipeline([
            ("tfidf", TfidfVectorizer(sublinear_tf=True)),
            ("clf", SVC(random_state=42))
        ]),
        "params": {
            "tfidf__ngram_range": [(1, 1), (1, 2)],
            "clf__kernel": ["linear", "rbf"],
            "clf__C": [0.5, 1.0, 5.0],
            "clf__gamma": ["scale", "auto"],
            "clf__class_weight": ["balanced", None]
        }
    },
    "Complement_NB": {
        "pipeline": Pipeline([
            ("tfidf", TfidfVectorizer(sublinear_tf=True)),
            ("clf", ComplementNB())
        ]),
        "params": {
            "tfidf__ngram_range": [(1, 1), (1, 2)],
            "clf__alpha": [0.01, 0.1, 0.5, 1.0, 2.0],
            "clf__norm": [True, False]
        }
    },
    "SGD_Classifier": {
        "pipeline": Pipeline([
            ("tfidf", TfidfVectorizer(sublinear_tf=True)),
            ("clf", SGDClassifier(loss="log_loss", max_iter=1000, random_state=42))
        ]),
        "params": {
            "tfidf__ngram_range": [(1, 1), (1, 2)],
            "clf__alpha": [1e-4, 1e-3, 1e-2],
            "clf__penalty": ["l2", "elasticnet"],
            "clf__class_weight": ["balanced", None]
        }
    },
    "Random_Forest": {
        "pipeline": Pipeline([
            ("tfidf", TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2))),
            ("clf", RandomForestClassifier(random_state=42, n_jobs=-1))
        ]),
        "params": {
            "clf__n_estimators": [100, 200],
            "clf__max_depth": [None, 30, 50],
            "clf__class_weight": ["balanced", None]
        }
    },
    "Extra_Trees": {
        "pipeline": Pipeline([
            ("tfidf", TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2))),
            ("clf", ExtraTreesClassifier(random_state=42, n_jobs=-1))
        ]),
        "params": {
            "clf__n_estimators": [100, 200],
            "clf__max_depth": [None, 30, 50],
            "clf__class_weight": ["balanced", None]
        }
    }
}

# -------------------------------------------------------------
# 3. 통합 평가 베이스 데이터프레임 구성 (val.csv 기준)
# -------------------------------------------------------------
eval_dfs = []
for val_name, df_item in val_dict.items():
    sub = df_item[["question", "label"]].copy()
    sub["데이터셋"] = val_name
    eval_dfs.append(sub)

combined_df = pd.concat(eval_dfs, ignore_index=True)
combined_df.rename(columns={"question": "질문", "label": "실제정답"}, inplace=True)

# 4. Stratified 5-Fold 교차 검증 및 최적 모델 최종 평가
benchmark_summary = []
model_wrong_sheets = {}

print("=================================================================")
print(" 7종 ML 모델 학습: ml_train.csv(Stratified 5-Fold) -> 최종 평가: val.csv")
print("=================================================================")

for name, exp in model_experiments.items():
    print(f"\n[1] {name} 5-Fold 교차 검증 및 전체 데이터 재학습 진행 중...")

    # refit=True 설정: 5-Fold 검증 결과 가장 우수한 파라미터로 X_train_full 전체를 자동 재학습
    grid = GridSearchCV(
        estimator=exp["pipeline"],
        param_grid=exp["params"],
        cv=skf,
        scoring="f1_macro",
        n_jobs=-1,
        return_train_score=True,
        refit=True,
        verbose=0
    )
    grid.fit(X_train_full, y_train_full)

    # 튜닝 상세 결과 저장
    pd.DataFrame(grid.cv_results_).sort_values(by="rank_test_score").to_csv(
        os.path.join(TUNING_DIR, f"{name}_5fold_tuning_results.csv"), index=False, encoding="utf-8-sig"
    )

    # 전체 데이터로 재학습된 최적 모델 객체 추출 및 저장
    best_pipe = grid.best_estimator_
    joblib.dump(best_pipe, os.path.join(MODEL_DIR, f"{name}_best.pkl"))

    best_cv_f1 = grid.best_score_

    summary_entry = {
        "Model": name,
        "CV_5Fold_Macro_F1": round(best_cv_f1, 4)
    }

    # 최종 독립 평가 세트(val.csv)에 대한 추론 및 성능 산출
    all_eval_preds = []
    log_msg_parts = [f"5-Fold CV F1: {best_cv_f1:.4f}"]

    for val_name, df_item in val_dict.items():
        preds = best_pipe.predict(df_item["question"])
        acc = accuracy_score(df_item["label"], preds)
        f1 = f1_score(df_item["label"], preds, average="macro")

        summary_entry[f"{val_name}_Acc"] = round(acc, 4)
        summary_entry[f"{val_name}_F1"] = round(f1, 4)
        all_eval_preds.extend(preds)
        log_msg_parts.append(f"{val_name} 평가 F1: {f1:.4f}")

    summary_entry["선정된_최적_파라미터"] = str(grid.best_params_)

    # 전체 평가셋(val.csv)에 대한 예측 컬럼 추가
    combined_df[f"{name}_예측답변"] = all_eval_preds

    # 해당 모델 오답 추출
    is_wrong = combined_df["실제정답"] != all_eval_preds
    wrong_df = combined_df.loc[is_wrong, ["데이터셋", "질문", "실제정답"]].copy()
    wrong_df["모델_오답예측"] = [pred for pred, w in zip(all_eval_preds, is_wrong) if w]
    model_wrong_sheets[name] = wrong_df

    summary_entry["총_오답건수(val)"] = len(wrong_df)
    benchmark_summary.append(summary_entry)

    print(f" -> {' | '.join(log_msg_parts)} (val 오답: {len(wrong_df)}건)")

# -------------------------------------------------------------
# 5. 적어도 1개 모델 이상 틀린 질문만 모은 통합 오답 시트 생성
# -------------------------------------------------------------
pred_cols = [f"{name}_예측답변" for name in model_experiments.keys()]

any_model_wrong = combined_df.apply(
    lambda row: any(row[col] != row["실제정답"] for col in pred_cols),
    axis=1
)

all_wrong_combined = combined_df.loc[any_model_wrong].copy()

for name in model_experiments.keys():
    col = f"{name}_예측답변"
    all_wrong_combined[f"{name}_결과"] = all_wrong_combined.apply(
        lambda r: f"X ({r[col]})" if r[col] != r["실제정답"] else "O",
        axis=1
    )
    all_wrong_combined.drop(columns=[col], inplace=True)

# -------------------------------------------------------------
# 6. 엑셀 파일 저장 (val_F1 기준 내림차순 정렬)
# -------------------------------------------------------------
sort_target = "val_F1"
final_summary_df = pd.DataFrame(benchmark_summary).sort_values(by=sort_target, ascending=False)
excel_output_path = os.path.join(OUTPUT_DIR, "validation_variants_comparison.xlsx")

with pd.ExcelWriter(excel_output_path, engine="openpyxl") as writer:
    final_summary_df.to_excel(writer, sheet_name="세트별_성능_요약", index=False)
    all_wrong_combined.to_excel(writer, sheet_name="틀린질문_통합비교", index=False)

    for model_name, w_df in model_wrong_sheets.items():
        sheet_name = model_name[:30]
        w_df.to_excel(writer, sheet_name=sheet_name, index=False)

print("\n=================================================================")
print(f"7종 ML 비교 분석 엑셀 저장 완료 -> {excel_output_path}")
print("=================================================================")