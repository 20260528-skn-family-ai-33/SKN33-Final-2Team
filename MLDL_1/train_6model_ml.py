import os
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import accuracy_score, f1_score, classification_report

# 6종 대표 모델
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.svm import LinearSVC
from sklearn.naive_bayes import ComplementNB
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier

# 1. 경로 설정 및 5개 데이터셋(Train, Val 3종, Test) 로드
DATA_DIR = "data"
MODEL_DIR = "ML_models"
TUNING_DIR = os.path.join(MODEL_DIR, "tuning_details")
OUTPUT_DIR = os.path.join(MODEL_DIR, "excel_reports")
os.makedirs(TUNING_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

train_df = pd.read_csv(os.path.join(DATA_DIR, "train.csv")).fillna({"query": ""})
test_df = pd.read_csv(os.path.join(DATA_DIR, "test.csv")).fillna({"query": ""})

# 3가지 버전의 Validation 데이터셋 로드 (결측치 방어)
val_dict = {
    "Val_기존": pd.read_csv(os.path.join(DATA_DIR, "val.csv")).fillna({"query": ""}),
    "Val_새문항": pd.read_csv(os.path.join(DATA_DIR, "new_val.csv")).fillna({"query": ""}),
    "Val_최신고난도": pd.read_csv(os.path.join(DATA_DIR, "hard_new_val.csv")).fillna({"query": ""}),
}

X_train, y_train = train_df["query"], train_df["label"]
X_test, y_test = test_df["query"], test_df["label"]

# 2. 6종 모델별 파라미터 탐색 그리드 정의
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
# 3. 통합 평가 베이스 데이터프레임 구성 (Val 3종 + Test)
# -------------------------------------------------------------
eval_dfs = []
for val_name, df_item in val_dict.items():
    sub = df_item[["query", "label"]].copy()
    sub["데이터셋"] = val_name
    eval_dfs.append(sub)

test_sub = test_df[["query", "label"]].copy()
test_sub["데이터셋"] = "Test"
eval_dfs.append(test_sub)

combined_df = pd.concat(eval_dfs, ignore_index=True)
combined_df.rename(columns={"query": "질문", "label": "실제정답"}, inplace=True)

# 4. 튜닝 실행 및 세트별 개별 성능 산출
benchmark_summary = []
model_wrong_sheets = {}

print("=================================================================")
print(" 6종 ML 모델 튜닝 및 [Val 3종 + Test] 독립 성능 평가 파이프라인")
print("=================================================================")

for name, exp in model_experiments.items():
    print(f"\n[1] {name} 튜닝 및 평가 진행 중...")

    grid = GridSearchCV(
        estimator=exp["pipeline"],
        param_grid=exp["params"],
        cv=5,
        scoring="f1_macro",
        n_jobs=-1,
        return_train_score=True,
        verbose=0
    )
    grid.fit(X_train, y_train)
    best_pipe = grid.best_estimator_

    # 최적 파이프라인 모델 저장 (.pkl)
    joblib.dump(best_pipe, os.path.join(MODEL_DIR, f"{name}_best.pkl"))

    summary_entry = {
        "Model": name,
        "CV_최고_F1": round(grid.best_score_, 4)
    }

    # 각 Validation 세트별 정확도 및 Macro F1 개별 계산 (동적 루프)
    all_eval_preds = []
    log_msg_parts = []

    for val_name, df_item in val_dict.items():
        preds = best_pipe.predict(df_item["query"])
        acc = accuracy_score(df_item["label"], preds)
        f1 = f1_score(df_item["label"], preds, average="macro")

        summary_entry[f"{val_name}_Acc"] = round(acc, 4)
        summary_entry[f"{val_name}_F1"] = round(f1, 4)
        all_eval_preds.extend(preds)
        log_msg_parts.append(f"{val_name} F1: {f1:.4f}")

    # Test 세트 평가
    test_preds = best_pipe.predict(X_test)
    test_acc = accuracy_score(y_test, test_preds)
    test_f1 = f1_score(y_test, test_preds, average="macro")

    summary_entry["Test_Acc"] = round(test_acc, 4)
    summary_entry["Test_F1"] = round(test_f1, 4)
    summary_entry["선정된_최적_파라미터"] = str(grid.best_params_)
    all_eval_preds.extend(test_preds)

    # 전체 평가셋에 대한 예측 컬럼 추가
    combined_df[f"{name}_예측답변"] = all_eval_preds

    # 해당 모델에서 틀린 질문 추출
    is_wrong = combined_df["실제정답"] != all_eval_preds
    wrong_df = combined_df.loc[is_wrong, ["데이터셋", "질문", "실제정답"]].copy()
    wrong_df["모델_오답예측"] = [pred for pred, w in zip(all_eval_preds, is_wrong) if w]
    model_wrong_sheets[name] = wrong_df

    summary_entry["총_오답건수(전체평가셋)"] = len(wrong_df)
    benchmark_summary.append(summary_entry)

    # 수정된 동적 로그 출력 (KeyError 방지)
    print(f" -> {' | '.join(log_msg_parts)} | Test F1: {test_f1:.4f}")

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
# 6. 엑셀 파일 저장
# -------------------------------------------------------------
# 최신 고난도 검증셋 F1 기준 내림차순 정렬
sort_target = "Val_최신고난도_F1" if "Val_최신고난도_F1" in benchmark_summary[0] else "Test_F1"
final_summary_df = pd.DataFrame(benchmark_summary).sort_values(by=sort_target, ascending=False)
excel_output_path = os.path.join(OUTPUT_DIR, "validation_variants_comparison.xlsx")

with pd.ExcelWriter(excel_output_path, engine="openpyxl") as writer:
    final_summary_df.to_excel(writer, sheet_name="세트별_성능_요약", index=False)
    all_wrong_combined.to_excel(writer, sheet_name="틀린질문_통합비교", index=False)

    for model_name, w_df in model_wrong_sheets.items():
        sheet_name = model_name[:30]
        w_df.to_excel(writer, sheet_name=sheet_name, index=False)

print("\n=================================================================")
print(f"세트별 비교 분석 엑셀 저장 완료 -> {excel_output_path}")
print("=================================================================")