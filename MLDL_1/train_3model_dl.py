import os
import re
import copy
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score

# -------------------------------------------------------------
# 1. 환경 설정 및 디렉토리 준비
# -------------------------------------------------------------
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DATA_DIR = "data"
MODEL_DIR = "DL_models"
OUTPUT_DIR = os.path.join(MODEL_DIR, "excel_reports")
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"[*] 사용 디바이스: {DEVICE}")

# -------------------------------------------------------------
# 2. 데이터셋 로드 및 라벨 매핑
# -------------------------------------------------------------
train_df = pd.read_csv(os.path.join(DATA_DIR, "train.csv")).fillna({"query": ""})
test_df = pd.read_csv(os.path.join(DATA_DIR, "test.csv")).fillna({"query": ""})

val_dict = {
    "Val_기존": pd.read_csv(os.path.join(DATA_DIR, "val.csv")).fillna({"query": ""}),
    "Val_새문항": pd.read_csv(os.path.join(DATA_DIR, "new_val.csv")).fillna({"query": ""}),
    "Val_최신고난도": pd.read_csv(os.path.join(DATA_DIR, "hard_new_val.csv")).fillna({"query": ""}),
}

LABEL_MAP = {"내부규정": 0, "기관정보": 1, "범위밖": 2}
INV_LABEL_MAP = {v: k for k, v in LABEL_MAP.items()}


# -------------------------------------------------------------
# 3. 토크나이저 및 단어 사전(Vocab) 구축 (CNN, LSTM용)
# -------------------------------------------------------------
def simple_tokenize(text):
    return re.findall(r"[가-힣a-zA-Z0-9]+", str(text))


vocab = {"<PAD>": 0, "<UNK>": 1}
# 독립적인 평가를 위해 Train 데이터만으로 어휘 사전 구축 (Data Leakage 방지)
# 만약 OOV 최소화를 위해 전체 텍스트를 다 넣으시려면 기존처럼 val_dict를 합치셔도 됩니다.
for text in train_df["query"]:
    for token in simple_tokenize(text):
        if token not in vocab:
            vocab[token] = len(vocab)

VOCAB_SIZE = len(vocab)
MAX_LEN = 40
print(f"[*] 구축된 어휘 사전 크기 (Train 기준): {VOCAB_SIZE}개")


def text_to_sequence(text, max_len=MAX_LEN):
    tokens = simple_tokenize(text)
    seq = [vocab.get(t, 1) for t in tokens][:max_len]
    if len(seq) < max_len:
        seq += [0] * (max_len - len(seq))
    return seq


# [1] 학습용(Train) 텐서 변환
X_train_seq = torch.tensor([text_to_sequence(t) for t in train_df["query"]], dtype=torch.long)
y_train_tensor = torch.tensor([LABEL_MAP[l] for l in train_df["label"]], dtype=torch.long)

tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=8000)
X_train_tfidf = torch.tensor(tfidf.fit_transform(train_df["query"]).toarray(), dtype=torch.float32)
TFIDF_DIM = X_train_tfidf.shape[1]

# [2] 학습 중 검증용(Test) 텐서 변환
X_test_seq = torch.tensor([text_to_sequence(t) for t in test_df["query"]], dtype=torch.long)
y_test_tensor = torch.tensor([LABEL_MAP[l] for l in test_df["label"]], dtype=torch.long)
X_test_tfidf = torch.tensor(tfidf.transform(test_df["query"]).toarray(), dtype=torch.float32)


# -------------------------------------------------------------
# 4. 딥러닝 3종 아키텍처 정의
# -------------------------------------------------------------
# 1) Deep MLP
class TextMLP(nn.Module):
    def __init__(self, input_dim, hidden1=256, hidden2=128, num_classes=3, dropout=0.3):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden1),
            nn.BatchNorm1d(hidden1),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden1, hidden2),
            nn.BatchNorm1d(hidden2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden2, num_classes)
        )

    def forward(self, x):
        return self.net(x)


# 2) TextCNN
class TextCNN(nn.Module):
    def __init__(self, vocab_size, embed_dim=128, num_filters=100, filter_sizes=(2, 3, 4), num_classes=3, dropout=0.3):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.convs = nn.ModuleList([
            nn.Conv1d(in_channels=embed_dim, out_channels=num_filters, kernel_size=fs)
            for fs in filter_sizes
        ])
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(len(filter_sizes) * num_filters, num_classes)

    def forward(self, x):
        embedded = self.embedding(x).permute(0, 2, 1)  # [B, embed_dim, seq_len]
        conved = [torch.relu(conv(embedded)) for conv in self.convs]
        pooled = [torch.max_pool1d(c, c.shape[2]).squeeze(2) for c in conved]
        cat = self.dropout(torch.cat(pooled, dim=1))
        return self.fc(cat)


# 3) BiLSTM
class BiLSTMClassifier(nn.Module):
    def __init__(self, vocab_size, embed_dim=128, hidden_dim=128, num_classes=3, dropout=0.3):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, batch_first=True, bidirectional=True)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_dim * 2, num_classes)

    def forward(self, x):
        embedded = self.dropout(self.embedding(x))
        _, (h_n, _) = self.lstm(embedded)
        hidden = torch.cat((h_n[-2, :, :], h_n[-1, :, :]), dim=1)
        return self.fc(self.dropout(hidden))


# -------------------------------------------------------------
# 5. 훈련 루프 (Train으로 학습 & Test로 최적 모델 검증/선택)
# -------------------------------------------------------------
def train_dl_model(model, train_x, train_y, test_x, test_y, epochs=15, batch_size=64, lr=0.001):
    model.to(DEVICE)
    dataset = torch.utils.data.TensorDataset(train_x, train_y)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    best_test_f1 = -1.0
    best_weights = None

    for epoch in range(epochs):
        model.train()
        for bx, by in loader:
            bx, by = bx.to(DEVICE), by.to(DEVICE)
            optimizer.zero_grad()
            out = model(bx)
            loss = criterion(out, by)
            loss.backward()
            optimizer.step()

        # 에폭별 Test 데이터셋으로 검증하여 최적 체크포인트 저장
        model.eval()
        with torch.no_grad():
            test_out = model(test_x.to(DEVICE))
            preds = test_out.argmax(dim=1).cpu().numpy()
            current_f1 = f1_score(test_y.numpy(), preds, average="macro")
            if current_f1 > best_test_f1:
                best_test_f1 = current_f1
                best_weights = copy.deepcopy(model.state_dict())

    if best_weights is not None:
        model.load_state_dict(best_weights)
    return model


# -------------------------------------------------------------
# 6. 모델 훈련 (Train/Test) 및 최종 독립 평가 (Val 3종)
# -------------------------------------------------------------
models_to_train = {
    "Deep_MLP": {
        "model": TextMLP(input_dim=TFIDF_DIM),
        "is_tfidf": True,
        "epochs": 15,
        "lr": 0.001
    },
    "TextCNN": {
        "model": TextCNN(vocab_size=VOCAB_SIZE),
        "is_tfidf": False,
        "epochs": 15,
        "lr": 0.002
    },
    "BiLSTM": {
        "model": BiLSTMClassifier(vocab_size=VOCAB_SIZE),
        "is_tfidf": False,
        "epochs": 15,
        "lr": 0.002
    }
}

# 오답 노트 구성을 위한 통합 데이터프레임 (검증에 쓰인 Test + 독립 평가용 Val 3종)
eval_dfs = []
test_sub = test_df[["query", "label"]].copy()
test_sub["데이터셋"] = "Test(학습검증)"
eval_dfs.append(test_sub)

for val_name, df_item in val_dict.items():
    sub = df_item[["query", "label"]].copy()
    sub["데이터셋"] = val_name
    eval_dfs.append(sub)

combined_df = pd.concat(eval_dfs, ignore_index=True)
combined_df.rename(columns={"query": "질문", "label": "실제정답"}, inplace=True)

benchmark_summary = []
model_wrong_sheets = {}

print("\n=================================================================")
print(" 3종 DL 모델: Train 학습 -> Test 검증 -> Val 3종 독립 평가")
print("=================================================================")

for name, cfg in models_to_train.items():
    print(f"\n[+] {name} 훈련 중 (검증 기준: Test 세트)...")
    is_tfidf = cfg["is_tfidf"]

    train_x = X_train_tfidf if is_tfidf else X_train_seq
    test_x = X_test_tfidf if is_tfidf else X_test_seq

    # 1) Train으로 학습하고 Test로 검증하여 Best 모델 획득
    trained_model = train_dl_model(
        cfg["model"], train_x, y_train_tensor, test_x, y_test_tensor,
        epochs=cfg["epochs"], lr=cfg["lr"]
    )

    # 최적 모델 가중치 저장
    torch.save(trained_model.state_dict(), os.path.join(MODEL_DIR, f"{name}_best.pt"))

    trained_model.eval()
    summary_entry = {"Model": name, "모델구분": "딥러닝(DL)"}
    all_eval_preds = []
    val_log_parts = []

    with torch.no_grad():
        # 2) 검증 데이터(Test) 최종 성능 기록
        test_preds = trained_model(test_x.to(DEVICE)).argmax(dim=1).cpu().numpy()
        test_pred_labels = [INV_LABEL_MAP[p] for p in test_preds]
        test_acc = accuracy_score(test_df["label"], test_pred_labels)
        test_f1 = f1_score(test_df["label"], test_pred_labels, average="macro")

        summary_entry["Test(검증)_Acc"] = round(test_acc, 4)
        summary_entry["Test(검증)_F1"] = round(test_f1, 4)
        all_eval_preds.extend(test_pred_labels)

        # 3) 학습 종료 후 Val 3종에 대한 독립 평가 수행
        for val_name, df_item in val_dict.items():
            if is_tfidf:
                bx = torch.tensor(tfidf.transform(df_item["query"]).toarray(), dtype=torch.float32).to(DEVICE)
            else:
                bx = torch.tensor([text_to_sequence(t) for t in df_item["query"]], dtype=torch.long).to(DEVICE)

            preds = trained_model(bx).argmax(dim=1).cpu().numpy()
            pred_labels = [INV_LABEL_MAP[p] for p in preds]

            acc = accuracy_score(df_item["label"], pred_labels)
            f1 = f1_score(df_item["label"], pred_labels, average="macro")

            summary_entry[f"{val_name}_Acc"] = round(acc, 4)
            summary_entry[f"{val_name}_F1"] = round(f1, 4)
            all_eval_preds.extend(pred_labels)
            val_log_parts.append(f"{val_name} F1: {f1:.4f}")

    # 오답 기록
    combined_df[f"{name}_예측답변"] = all_eval_preds
    is_wrong = combined_df["실제정답"] != all_eval_preds
    wrong_df = combined_df.loc[is_wrong, ["데이터셋", "질문", "실제정답"]].copy()
    wrong_df["모델_오답예측"] = [pred for pred, w in zip(all_eval_preds, is_wrong) if w]
    model_wrong_sheets[name] = wrong_df

    # 독립 평가셋(Val 3종)만의 오답 건수와 전체 오답 건수 함께 기록
    val_only_wrong_count = (wrong_df["데이터셋"] != "Test(학습검증)").sum()
    summary_entry["독립평가(Val3종)_오답건수"] = int(val_only_wrong_count)
    summary_entry["총_오답건수(Test포함)"] = len(wrong_df)
    benchmark_summary.append(summary_entry)

    print(f" -> [검증] Test F1: {test_f1:.4f} || [독립평가] {' | '.join(val_log_parts)}")

# -------------------------------------------------------------
# 7. 통합 오답 시트 및 엑셀 저장
# -------------------------------------------------------------
pred_cols = [f"{name}_예측답변" for name in models_to_train.keys()]
any_model_wrong = combined_df.apply(lambda row: any(row[col] != row["실제정답"] for col in pred_cols), axis=1)
all_wrong_combined = combined_df.loc[any_model_wrong].copy()

for name in models_to_train.keys():
    col = f"{name}_예측답변"
    all_wrong_combined[f"{name}_결과"] = all_wrong_combined.apply(
        lambda r: f"X ({r[col]})" if r[col] != r["실제정답"] else "O", axis=1
    )
    all_wrong_combined.drop(columns=[col], inplace=True)

# 정렬 기준은 독립 평가의 핵심 지표인 Val_최신고난도_F1 유지
final_summary_df = pd.DataFrame(benchmark_summary).sort_values(by="Val_최신고난도_F1", ascending=False)
excel_output_path = os.path.join(OUTPUT_DIR, "dl_validation_variants_comparison.xlsx")

with pd.ExcelWriter(excel_output_path, engine="openpyxl") as writer:
    final_summary_df.to_excel(writer, sheet_name="세트별_성능_요약", index=False)
    all_wrong_combined.to_excel(writer, sheet_name="틀린질문_통합비교", index=False)
    for model_name, w_df in model_wrong_sheets.items():
        w_df.to_excel(writer, sheet_name=model_name[:30], index=False)

print("\n=================================================================")
print(f"[*] 딥러닝 세트별 비교 분석 엑셀 저장 완료 -> {excel_output_path}")
print("=================================================================")