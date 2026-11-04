"""5개 딥러닝/임베딩 분류 모델 비교 실험.

포함 모델 (5종):
    1. Deep MLP (TF-IDF Feature 기반 심층신경망)
    2. TextCNN
    3. BiLSTM
    4. KLUE RoBERTa (Pre-trained Fine-tuning)
    5. E5 + Logistic Regression (사전학습 트랜스포머 임베딩 + 선형 분류기)

데이터 분할 역할:
    train.csv: 학습
    test.csv: 학습 중 상태 확인 및 딥러닝 모델의 최적 가중치 선택
    val.csv: 최종 성능 평가와 오답 분석 리포트 생성

"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader, Dataset

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parent
    / "DL_models"
    / "five_model_comparison"
)
DEFAULT_ROBERTA_MODEL = "klue/roberta-base"
DEFAULT_E5_MODEL = "intfloat/multilingual-e5-base"
SEED = 42


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_frame(path: Path) -> pd.DataFrame:
    """CSV에서 question과 label 두 컬럼만 읽고 검증한다."""
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    frame = pd.read_csv(path)
    required = {"question", "label"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path}에 필요한 컬럼이 없습니다: {sorted(missing)}")

    frame = frame[["question", "label"]].copy()
    if frame.empty:
        raise ValueError(f"{path}에 데이터가 없습니다.")

    if frame["label"].isna().any():
        raise ValueError(f"{path}에 label이 비어 있는 행이 있습니다.")

    frame["question"] = frame["question"].fillna("").astype(str)
    frame["label"] = frame["label"].astype(str)

    if frame["label"].str.strip().eq("").any():
        raise ValueError(f"{path}에 label이 비어 있는 행이 있습니다.")

    return frame


def make_label_maps(train_df: pd.DataFrame) -> Tuple[Dict[str, int], Dict[int, str]]:
    labels = sorted(train_df["label"].unique())
    if len(labels) < 2:
        raise ValueError(f"분류를 위해 2개 이상의 label이 필요합니다: {labels}")

    label_to_id = {label: index for index, label in enumerate(labels)}
    id_to_label = {index: label for label, index in label_to_id.items()}
    return label_to_id, id_to_label


def encode_labels(frame: pd.DataFrame, label_to_id: Dict[str, int]) -> np.ndarray:
    unknown = sorted(set(frame["label"]) - set(label_to_id))
    if unknown:
        raise ValueError(f"학습 데이터에 없는 label이 있습니다: {unknown}")
    return frame["label"].map(label_to_id).to_numpy(dtype=np.int64)


def evaluate_predictions(
    method: str,
    dataset_name: str,
    frame: pd.DataFrame,
    predictions: Sequence[int],
    id_to_label: Dict[int, str],
) -> Dict[str, object]:
    """최종 평가용 지표를 계산한다. (val.csv에만 사용)"""
    y_true = frame["label"].to_numpy()
    predicted_labels = np.asarray([id_to_label[int(value)] for value in predictions])

    return {
        "방법": method,
        "데이터셋": dataset_name,
        "정확도": round(float(accuracy_score(y_true, predicted_labels)), 4),
        "Macro F1": round(
            float(f1_score(y_true, predicted_labels, average="macro", zero_division=0)),
            4,
        ),
        "표본수": len(frame),
    }


def print_test_score(
    method: str,
    test_df: pd.DataFrame,
    predictions: Sequence[int],
    label_to_id: Dict[str, int],
) -> None:
    """test.csv 점수를 콘솔에만 출력한다."""
    true_ids = encode_labels(test_df, label_to_id)
    score = f1_score(true_ids, predictions, average="macro", zero_division=0)
    print(f"[학습 확인] {method}: test Macro F1={score:.4f}")


def simple_tokenize(text: str) -> List[str]:
    return re.findall(r"[가-힣a-zA-Z0-9]+", str(text))


# ==========================================
# 1. Deep MLP 모델
# ==========================================
class TextMLP(nn.Module):
    def __init__(self, input_dim: int, num_classes: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.net(inputs)


# ==========================================
# 2. TextCNN 모델
# ==========================================
class TextCNN(nn.Module):
    def __init__(self, vocab_size: int, num_classes: int):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, 128, padding_idx=0)
        self.convs = nn.ModuleList([nn.Conv1d(128, 100, size) for size in (2, 3, 4)])
        self.dropout = nn.Dropout(0.3)
        self.classifier = nn.Linear(300, num_classes)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(inputs).permute(0, 2, 1)
        pooled = [torch.relu(conv(embedded)).amax(dim=2) for conv in self.convs]
        combined = torch.cat(pooled, dim=1)
        return self.classifier(self.dropout(combined))


# ==========================================
# 3. BiLSTM 모델
# ==========================================
class BiLSTMClassifier(nn.Module):
    def __init__(self, vocab_size: int, num_classes: int):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, 128, padding_idx=0)
        self.lstm = nn.LSTM(128, 128, batch_first=True, bidirectional=True)
        self.dropout = nn.Dropout(0.3)
        self.classifier = nn.Linear(256, num_classes)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        embedded = self.dropout(self.embedding(inputs))
        _, (hidden, _) = self.lstm(embedded)
        hidden = torch.cat((hidden[-2], hidden[-1]), dim=1)
        return self.classifier(self.dropout(hidden))


def build_vocab(texts: Iterable[str]) -> Dict[str, int]:
    vocab = {"<PAD>": 0, "<UNK>": 1}
    for text in texts:
        for token in simple_tokenize(text):
            vocab.setdefault(token, len(vocab))
    return vocab


def text_to_sequence(text: str, vocab: Dict[str, int], max_length: int = 40) -> List[int]:
    sequence = [vocab.get(token, 1) for token in simple_tokenize(text)[:max_length]]
    return sequence + [0] * (max_length - len(sequence))


def train_torch_text_model(
    model: nn.Module,
    train_x: torch.Tensor,
    train_y: torch.Tensor,
    test_x: torch.Tensor,
    test_y: torch.Tensor,
    output_path: Path,
    epochs: int,
    learning_rate: float,
) -> Tuple[str, nn.Module]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    loader = DataLoader(
        torch.utils.data.TensorDataset(train_x, train_y),
        batch_size=64,
        shuffle=True,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()

    best_f1 = -1.0
    best_state = None

    for epoch in range(epochs):
        model.train()
        for batch_x, batch_y in loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            optimizer.zero_grad()
            loss = criterion(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()

        # test.csv로 학습 상태를 확인하고 최적 가중치 갱신
        model.eval()
        with torch.no_grad():
            predictions = model(test_x.to(device)).argmax(dim=1).cpu().numpy()

        current_f1 = f1_score(test_y.numpy(), predictions, average="macro", zero_division=0)
        print(f"[{model.__class__.__name__}] epoch {epoch + 1:02d}/{epochs:02d}, test Macro F1={current_f1:.4f}")

        if current_f1 > best_f1:
            best_f1 = current_f1
            best_state = copy.deepcopy(model.state_dict())

    if best_state is not None:
        model.load_state_dict(best_state)

    torch.save(model.state_dict(), output_path)
    return model.__class__.__name__, model


def predict_torch(
    model_info: Tuple[nn.Module, Dict[str, int], int],
    frame: pd.DataFrame,
) -> np.ndarray:
    model, vocab, max_length = model_info
    device = next(model.parameters()).device

    inputs = torch.tensor(
        [text_to_sequence(text, vocab, max_length) for text in frame["question"]],
        dtype=torch.long,
    ).to(device)

    model.eval()
    with torch.no_grad():
        return model(inputs).argmax(dim=1).cpu().numpy()


# ==========================================
# 4. E5 + Logistic Regression
# ==========================================
def encode_e5(texts: Iterable[str], model_name: str, batch_size: int = 32) -> np.ndarray:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("E5 실행에는 sentence-transformers가 필요합니다: pip install sentence-transformers") from exc

    model = SentenceTransformer(model_name)
    prefixed = [f"query: {text}" for text in texts]
    embeddings = model.encode(
        prefixed,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return np.asarray(embeddings, dtype=np.float32)


def train_e5_logistic(
    train_df: pd.DataFrame,
    label_to_id: Dict[str, int],
    output_dir: Path,
    model_name: str,
) -> Tuple[str, object]:
    train_embeddings = encode_e5(train_df["question"], model_name)
    classifier = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=SEED)
    classifier.fit(train_embeddings, encode_labels(train_df, label_to_id))

    joblib.dump({"model_name": model_name, "classifier": classifier}, output_dir / "e5_logistic_regression.joblib")
    return "E5 + Logistic Regression", (model_name, classifier)


# ==========================================
# 5. KLUE RoBERTa
# ==========================================
class EncodedTextDataset(Dataset):
    def __init__(self, encodings: Dict[str, Sequence[Sequence[int]]], labels: np.ndarray):
        self.encodings = encodings
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int) -> Dict[str, torch.Tensor]:
        item = {key: torch.tensor(value[index], dtype=torch.long) for key, value in self.encodings.items()}
        item["labels"] = self.labels[index]
        return item


def tokenize_texts(tokenizer: object, texts: Iterable[str], max_length: int) -> Dict[str, Sequence[Sequence[int]]]:
    return tokenizer(list(texts), padding="max_length", truncation=True, max_length=max_length)


def roberta_predictions(model: torch.nn.Module, loader: DataLoader, device: torch.device) -> np.ndarray:
    model.eval()
    predictions: List[int] = []
    with torch.no_grad():
        for batch in loader:
            inputs = {key: value.to(device) for key, value in batch.items() if key != "labels"}
            batch_predictions = model(**inputs).logits.argmax(dim=1).cpu().tolist()
            predictions.extend(batch_predictions)
    return np.asarray(predictions)


def train_klue_roberta(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    label_to_id: Dict[str, int],
    output_dir: Path,
    model_name: str,
    epochs: int,
    max_length: int,
) -> Tuple[str, object]:
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("KLUE RoBERTa 실행에는 transformers가 필요합니다: pip install transformers") from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(label_to_id),
        id2label={index: label for label, index in label_to_id.items()},
        label2id=label_to_id,
    ).to(device)

    train_labels = encode_labels(train_df, label_to_id)
    test_labels = encode_labels(test_df, label_to_id)

    train_dataset = EncodedTextDataset(tokenize_texts(tokenizer, train_df["question"], max_length), train_labels)
    test_dataset = EncodedTextDataset(tokenize_texts(tokenizer, test_df["question"], max_length), test_labels)

    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=32)

    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5, weight_decay=0.01)

    best_f1 = -1.0
    best_state = None

    for epoch in range(epochs):
        model.train()
        for batch in train_loader:
            batch = {key: value.to(device) for key, value in batch.items()}
            optimizer.zero_grad()
            loss = model(**batch).loss
            loss.backward()
            optimizer.step()

        # test.csv로 학습 상태를 확인하고 최적 가중치 선택
        predictions = roberta_predictions(model, test_loader, device)
        current_f1 = f1_score(test_labels, predictions, average="macro", zero_division=0)
        print(f"[KLUE RoBERTa] epoch {epoch + 1:02d}/{epochs:02d}, test Macro F1={current_f1:.4f}")

        if current_f1 > best_f1:
            best_f1 = current_f1
            best_state = copy.deepcopy(model.state_dict())

    if best_state is not None:
        model.load_state_dict(best_state)

    model.save_pretrained(output_dir / "klue_roberta")
    tokenizer.save_pretrained(output_dir / "klue_roberta")

    return "KLUE RoBERTa", (tokenizer, model, max_length)


def predict_roberta(model_info: Tuple[object, torch.nn.Module, int], frame: pd.DataFrame) -> np.ndarray:
    tokenizer, model, max_length = model_info
    device = next(model.parameters()).device

    dataset = EncodedTextDataset(
        tokenize_texts(tokenizer, frame["question"], max_length),
        np.zeros(len(frame), dtype=np.int64),
    )
    loader = DataLoader(dataset, batch_size=32)
    return roberta_predictions(model, loader, device)


# ==========================================
# CLI 및 파이프라인 제어
# ==========================================
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--roberta-model", default=DEFAULT_ROBERTA_MODEL)
    parser.add_argument("--e5-model", default=DEFAULT_E5_MODEL)
    parser.add_argument("--roberta-epochs", type=int, default=3)
    parser.add_argument("--mlp-epochs", type=int, default=15)
    parser.add_argument("--cnn-rnn-epochs", type=int, default=15)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--skip-roberta", action="store_true")
    parser.add_argument("--skip-e5", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    set_seed()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    train_df = load_frame(args.data_dir / "train.csv")
    test_df = load_frame(args.data_dir / "test.csv")
    val_df = load_frame(args.data_dir / "val.csv")

    label_to_id, id_to_label = make_label_maps(train_df)
    encode_labels(test_df, label_to_id)
    encode_labels(val_df, label_to_id)

    (args.output_dir / "label_map.json").write_text(
        json.dumps({"label_to_id": label_to_id, "id_to_label": id_to_label}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    device_name = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"사용 디바이스: {device_name}")
    print(f"클래스 ({len(label_to_id)}개): {list(label_to_id)}")

    trained_models: Dict[str, object] = {}

    # 1. Deep MLP (SVM 없이 TF-IDF 단독 추출기를 학습 및 변환기로 활용)
    print("\n--- [1/5 Deep MLP 학습 및 검증] ---")
    tfidf_vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        sublinear_tf=True,
        max_features=20000,
    )
    train_tfidf = torch.tensor(
        tfidf_vectorizer.fit_transform(train_df["question"]).toarray(),
        dtype=torch.float32,
    )
    test_tfidf = torch.tensor(
        tfidf_vectorizer.transform(test_df["question"]).toarray(),
        dtype=torch.float32,
    )

    train_labels = torch.tensor(encode_labels(train_df, label_to_id), dtype=torch.long)
    test_labels = torch.tensor(encode_labels(test_df, label_to_id), dtype=torch.long)

    joblib.dump(tfidf_vectorizer, args.output_dir / "tfidf_vectorizer.joblib")

    mlp = TextMLP(train_tfidf.shape[1], len(label_to_id))
    _, mlp = train_torch_text_model(
        mlp,
        train_tfidf,
        train_labels,
        test_tfidf,
        test_labels,
        args.output_dir / "deep_mlp.pt",
        epochs=args.mlp_epochs,
        learning_rate=1e-3,
    )
    # MLP 모델과 변환기 함께 저장
    trained_models["Deep MLP"] = (mlp, tfidf_vectorizer)

    # 2. TextCNN 및 3. BiLSTM
    print("\n--- [2/5 TextCNN & 3/5 BiLSTM 학습 및 검증] ---")
    vocab = build_vocab(train_df["question"])
    train_sequences = torch.tensor([text_to_sequence(text, vocab) for text in train_df["question"]], dtype=torch.long)
    test_sequences = torch.tensor([text_to_sequence(text, vocab) for text in test_df["question"]], dtype=torch.long)

    cnn = TextCNN(len(vocab), len(label_to_id))
    _, cnn = train_torch_text_model(
        cnn,
        train_sequences,
        train_labels,
        test_sequences,
        test_labels,
        args.output_dir / "text_cnn.pt",
        epochs=args.cnn_rnn_epochs,
        learning_rate=2e-3,
    )
    trained_models["TextCNN"] = (cnn, vocab, 40)

    bilstm = BiLSTMClassifier(len(vocab), len(label_to_id))
    _, bilstm = train_torch_text_model(
        bilstm,
        train_sequences,
        train_labels,
        test_sequences,
        test_labels,
        args.output_dir / "bilstm.pt",
        epochs=args.cnn_rnn_epochs,
        learning_rate=2e-3,
    )
    trained_models["BiLSTM"] = (bilstm, vocab, 40)

    # 4. KLUE RoBERTa
    if not args.skip_roberta:
        print("\n--- [4/5 KLUE RoBERTa Fine-tuning 학습 및 검증] ---")
        method, model = train_klue_roberta(
            train_df,
            test_df,
            label_to_id,
            args.output_dir,
            args.roberta_model,
            args.roberta_epochs,
            args.max_length,
        )
        trained_models[method] = model

    # 5. E5 + Logistic Regression
    if not args.skip_e5:
        print("\n--- [5/5 E5 + Logistic Regression 학습 및 검증] ---")
        method, model = train_e5_logistic(
            train_df,
            label_to_id,
            args.output_dir,
            args.e5_model,
        )
        trained_models[method] = model

        model_name, classifier = model
        test_embeddings = encode_e5(test_df["question"], model_name)
        test_predictions = classifier.predict(test_embeddings)
        print_test_score(method, test_df, test_predictions, label_to_id)

    # ==========================================
    # val.csv를 사용한 최종 성능 평가 및 오답 분석
    # ==========================================
    print("\n" + "=" * 50)
    print(">>> val.csv 기반 5개 모델 최종 평가 및 오답 엑셀 리포트 생성")
    print("=" * 50)

    summary_rows: List[Dict[str, object]] = []
    val_combined_df = val_df[["question", "label"]].copy()
    val_combined_df.rename(columns={"question": "질문", "label": "실제정답"}, inplace=True)
    model_wrong_sheets: Dict[str, pd.DataFrame] = {}

    for method, model_info in trained_models.items():
        if method == "Deep MLP":
            model, vec = model_info
            features = torch.tensor(vec.transform(val_df["question"]).toarray(), dtype=torch.float32)
            device = next(model.parameters()).device
            model.eval()
            with torch.no_grad():
                predictions = model(features.to(device)).argmax(dim=1).cpu().numpy()

        elif method in {"TextCNN", "BiLSTM"}:
            predictions = predict_torch(model_info, val_df)

        elif method == "E5 + Logistic Regression":
            m_name, classifier = model_info
            embeddings = encode_e5(val_df["question"], m_name)
            predictions = classifier.predict(embeddings)

        else:  # KLUE RoBERTa
            predictions = predict_roberta(model_info, val_df)

        # val.csv 결과 지표 추가
        summary_rows.append(evaluate_predictions(method, "val", val_df, predictions, id_to_label))

        predicted_labels = [id_to_label[int(value)] for value in predictions]
        val_combined_df[f"{method}_예측답변"] = predicted_labels

        is_wrong = val_df["label"].to_numpy() != np.asarray(predicted_labels)
        wrong_df = val_df.loc[is_wrong, ["question", "label"]].copy()
        wrong_df.rename(columns={"question": "질문", "label": "실제정답"}, inplace=True)
        wrong_df["모델_오답예측"] = [p for p, w in zip(predicted_labels, is_wrong) if w]

        safe_sheet_name = method.replace(" + ", "_").replace(" ", "_")[:30]
        model_wrong_sheets[safe_sheet_name] = wrong_df

    # 통합 오답 리스트 추출 (한 모델이라도 틀린 질문)
    pred_cols = [f"{method}_예측답변" for method in trained_models]
    any_model_wrong = val_combined_df.apply(
        lambda row: any(row[col] != row["실제정답"] for col in pred_cols),
        axis=1,
    )
    all_wrong_combined = val_combined_df.loc[any_model_wrong].copy()

    for method in trained_models:
        col = f"{method}_예측답변"
        all_wrong_combined[f"{method}_결과"] = all_wrong_combined.apply(
            lambda row: f"X ({row[col]})" if row[col] != row["실제정답"] else "O",
            axis=1,
        )
        all_wrong_combined.drop(columns=[col], inplace=True)

    summary_df = pd.DataFrame(summary_rows).sort_values(by="Macro F1", ascending=False)
    report_path = args.output_dir / "five_model_val_comparison.xlsx"

    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="성능요약", index=False)
        all_wrong_combined.to_excel(writer, sheet_name="틀린질문_통합비교", index=False)
        for sheet_name, wrong_df in model_wrong_sheets.items():
            wrong_df.to_excel(writer, sheet_name=sheet_name, index=False)

    print("\n[최종 평가 지표 (val.csv 기준)]")
    print(summary_df.to_string(index=False))
    print(f"\n[완료] 결과 파일 저장 위치: {report_path}")


if __name__ == "__main__":
    main()