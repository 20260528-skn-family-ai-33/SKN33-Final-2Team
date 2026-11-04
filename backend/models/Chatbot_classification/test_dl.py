"""저장된 5개 딥러닝/임베딩 분류 모델을 로드하여 new_val.csv를 평가하고
성능 요약 및 오답 분석 엑셀 리포트를 생성하는 스크립트.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader, Dataset

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_MODEL_DIR = (
    Path(__file__).resolve().parent
    / "DL_models"
    / "five_model_comparison"
)


# ==========================================
# 1. 모델 아키텍처 정의 (학습 코드와 동일)
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


class EncodedTextDataset(Dataset):
    def __init__(self, encodings: Dict[str, Sequence[Sequence[int]]]):
        self.encodings = encodings

    def __len__(self) -> int:
        return len(next(iter(self.encodings.values())))

    def __getitem__(self, index: int) -> Dict[str, torch.Tensor]:
        return {key: torch.tensor(value[index], dtype=torch.long) for key, value in self.encodings.items()}


# ==========================================
# 2. 전처리 및 유틸리티 함수
# ==========================================
def simple_tokenize(text: str) -> List[str]:
    return re.findall(r"[가-힣a-zA-Z0-9]+", str(text))


def build_vocab(texts: Iterable[str]) -> Dict[str, int]:
    vocab = {"<PAD>": 0, "<UNK>": 1}
    for text in texts:
        for token in simple_tokenize(text):
            vocab.setdefault(token, len(vocab))
    return vocab


def text_to_sequence(text: str, vocab: Dict[str, int], max_length: int = 40) -> List[int]:
    sequence = [vocab.get(token, 1) for token in simple_tokenize(text)[:max_length]]
    return sequence + [0] * (max_length - len(sequence))


def load_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    frame = pd.read_csv(path)
    required = {"question", "label"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path}에 필요한 컬럼이 없습니다: {sorted(missing)}")

    frame = frame[["question", "label"]].copy()
    frame["question"] = frame["question"].fillna("").astype(str)
    frame["label"] = frame["label"].astype(str)
    return frame


def evaluate_predictions(
    method: str,
    frame: pd.DataFrame,
    predictions: Sequence[int],
    id_to_label: Dict[int, str],
) -> Dict[str, object]:
    y_true = frame["label"].to_numpy()
    predicted_labels = np.asarray([id_to_label[int(value)] for value in predictions])

    return {
        "방법": method,
        "정확도": round(float(accuracy_score(y_true, predicted_labels)), 4),
        "Macro F1": round(
            float(f1_score(y_true, predicted_labels, average="macro", zero_division=0)),
            4,
        ),
        "표본수": len(frame),
    }


# ==========================================
# 3. 모델별 추론 로직
# ==========================================
def predict_mlp(model: nn.Module, vectorizer: object, texts: pd.Series, device: torch.device) -> np.ndarray:
    features = torch.tensor(vectorizer.transform(texts).toarray(), dtype=torch.float32).to(device)
    model.eval()
    with torch.no_grad():
        return model(features).argmax(dim=1).cpu().numpy()


def predict_sequence_model(
    model: nn.Module,
    vocab: Dict[str, int],
    texts: pd.Series,
    device: torch.device,
    max_length: int = 40,
) -> np.ndarray:
    inputs = torch.tensor(
        [text_to_sequence(text, vocab, max_length) for text in texts],
        dtype=torch.long,
    ).to(device)
    model.eval()
    with torch.no_grad():
        return model(inputs).argmax(dim=1).cpu().numpy()


def predict_e5(model_info: Tuple[str, object], texts: pd.Series) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    model_name, classifier = model_info
    model = SentenceTransformer(model_name)
    prefixed = [f"query: {text}" for text in texts]
    embeddings = model.encode(
        prefixed,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return classifier.predict(np.asarray(embeddings, dtype=np.float32))


def predict_roberta(
    model_dir: Path,
    texts: pd.Series,
    device: torch.device,
    max_length: int = 128,
) -> np.ndarray:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(device)
    model.eval()

    encodings = tokenizer(list(texts), padding="max_length", truncation=True, max_length=max_length)
    dataset = EncodedTextDataset(encodings)
    loader = DataLoader(dataset, batch_size=32)

    predictions: List[int] = []
    with torch.no_grad():
        for batch in loader:
            inputs = {k: v.to(device) for k, v in batch.items()}
            logits = model(**inputs).logits
            predictions.extend(logits.argmax(dim=1).cpu().tolist())

    return np.asarray(predictions)


# ==========================================
# 4. 메인 실행 파이프라인
# ==========================================
def main() -> None:
    parser = argparse.ArgumentParser(description="저장된 모델로 new_val.csv 평가")
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_DATA_DIR / "new_val.csv")
    parser.add_argument("--train-file", type=Path, default=DEFAULT_DATA_DIR / "train.csv")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--output-file", type=Path, default=None)
    parser.add_argument("--max-length", type=int, default=128)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"평가 실행 디바이스: {device}")

    eval_df = load_frame(args.eval_file)
    print(f"평가 데이터 로드 완료 ({args.eval_file}): {len(eval_df)}건")

    # 레이블 맵 로드
    label_map_path = args.model_dir / "label_map.json"
    if not label_map_path.exists():
        raise FileNotFoundError(f"레이블 매핑 파일이 없습니다: {label_map_path}")

    label_maps = json.loads(label_map_path.read_text(encoding="utf-8"))
    label_to_id: Dict[str, int] = label_maps["label_to_id"]
    id_to_label: Dict[int, str] = {int(k): v for k, v in label_maps["id_to_label"].items()}
    num_classes = len(label_to_id)

    # TextCNN / BiLSTM용 vocab 복원 (train.csv 기준)
    vocab = None
    if (args.model_dir / "text_cnn.pt").exists() or (args.model_dir / "bilstm.pt").exists():
        train_df = load_frame(args.train_file)
        vocab = build_vocab(train_df["question"])

    model_predictions: Dict[str, np.ndarray] = {}

    # 1. Deep MLP 로드 및 예측
    mlp_path = args.model_dir / "deep_mlp.pt"
    vec_path = args.model_dir / "tfidf_vectorizer.joblib"
    if mlp_path.exists() and vec_path.exists():
        print("-> [1/5] Deep MLP 모델 평가 중...")
        vectorizer = joblib.load(vec_path)
        mlp = TextMLP(len(vectorizer.get_feature_names_out()), num_classes).to(device)
        mlp.load_state_dict(torch.load(mlp_path, map_location=device))
        model_predictions["Deep MLP"] = predict_mlp(mlp, vectorizer, eval_df["question"], device)

    # 2. TextCNN 로드 및 예측
    cnn_path = args.model_dir / "text_cnn.pt"
    if cnn_path.exists() and vocab is not None:
        print("-> [2/5] TextCNN 모델 평가 중...")
        cnn = TextCNN(len(vocab), num_classes).to(device)
        cnn.load_state_dict(torch.load(cnn_path, map_location=device))
        model_predictions["TextCNN"] = predict_sequence_model(cnn, vocab, eval_df["question"], device)

    # 3. BiLSTM 로드 및 예측
    bilstm_path = args.model_dir / "bilstm.pt"
    if bilstm_path.exists() and vocab is not None:
        print("-> [3/5] BiLSTM 모델 평가 중...")
        bilstm = BiLSTMClassifier(len(vocab), num_classes).to(device)
        bilstm.load_state_dict(torch.load(bilstm_path, map_location=device))
        model_predictions["BiLSTM"] = predict_sequence_model(bilstm, vocab, eval_df["question"], device)

    # 4. KLUE RoBERTa 로드 및 예측
    roberta_dir = args.model_dir / "klue_roberta"
    if roberta_dir.exists():
        print("-> [4/5] KLUE RoBERTa 모델 평가 중...")
        model_predictions["KLUE RoBERTa"] = predict_roberta(
            roberta_dir, eval_df["question"], device, max_length=args.max_length
        )

    # 5. E5 + Logistic Regression 로드 및 예측
    e5_path = args.model_dir / "e5_logistic_regression.joblib"
    if e5_path.exists():
        print("-> [5/5] E5 + Logistic Regression 모델 평가 중...")
        e5_artifact = joblib.load(e5_path)
        model_predictions["E5 + Logistic Regression"] = predict_e5(
            (e5_artifact["model_name"], e5_artifact["classifier"]),
            eval_df["question"],
        )

    if not model_predictions:
        raise RuntimeError(f"{args.model_dir} 경로에서 로드 가능한 모델 가중치를 찾지 못했습니다.")

    # ==========================================
    # 성능 집계 및 엑셀 리포트 작성
    # ==========================================
    summary_rows: List[Dict[str, object]] = []
    combined_df = eval_df[["question", "label"]].copy()
    combined_df.rename(columns={"question": "질문", "label": "실제정답"}, inplace=True)
    model_wrong_sheets: Dict[str, pd.DataFrame] = {}

    for method, preds in model_predictions.items():
        summary_rows.append(evaluate_predictions(method, eval_df, preds, id_to_label))

        pred_labels = [id_to_label[int(idx)] for idx in preds]
        combined_df[f"{method}_예측답변"] = pred_labels

        is_wrong = eval_df["label"].to_numpy() != np.asarray(pred_labels)
        wrong_df = eval_df.loc[is_wrong, ["question", "label"]].copy()
        wrong_df.rename(columns={"question": "질문", "label": "실제정답"}, inplace=True)
        wrong_df["모델_오답예측"] = [p for p, w in zip(pred_labels, is_wrong) if w]

        safe_sheet_name = method.replace(" + ", "_").replace(" ", "_")[:30]
        model_wrong_sheets[safe_sheet_name] = wrong_df

    # 모델 간 비교 컬럼 생성 (하나라도 틀린 질문 시트)
    pred_cols = [f"{method}_예측답변" for method in model_predictions]
    any_model_wrong = combined_df.apply(
        lambda row: any(row[col] != row["실제정답"] for col in pred_cols),
        axis=1,
    )
    all_wrong_combined = combined_df.loc[any_model_wrong].copy()

    for method in model_predictions:
        col = f"{method}_예측답변"
        all_wrong_combined[f"{method}_결과"] = all_wrong_combined.apply(
            lambda row: f"X ({row[col]})" if row[col] != row["실제정답"] else "O",
            axis=1,
        )
        all_wrong_combined.drop(columns=[col], inplace=True)

    summary_df = pd.DataFrame(summary_rows).sort_values(by="Macro F1", ascending=False)

    report_path = args.output_file or (args.model_dir / "new_val_evaluation_report.xlsx")
    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="성능요약", index=False)
        all_wrong_combined.to_excel(writer, sheet_name="틀린질문_통합비교", index=False)
        for sheet_name, wrong_df in model_wrong_sheets.items():
            wrong_df.to_excel(writer, sheet_name=sheet_name, index=False)

    print("\n" + "=" * 50)
    print(f"[new_val.csv 최종 평가 결과]")
    print(summary_df.to_string(index=False))
    print(f"\n[완료] 결과 엑셀 리포트 저장 위치: {report_path}")
    print("=" * 50)


if __name__ == "__main__":
    main()