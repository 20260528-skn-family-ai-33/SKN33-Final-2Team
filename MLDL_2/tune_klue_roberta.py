"""klue/roberta-base를 튜닝하고 val Macro F1 최고 모델과 평가 기록을 저장한다.

train.csv로 학습하고 test.csv와 val.csv의 지표를 매 epoch 기록한다.
val.csv의 Macro F1로 설정과 epoch을 고른다.
epoch별 지표는 tuning_history.csv에, 실행 조건과 선택 모델의 val 상세 결과는 별도 파일에 저장한다.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import itertools
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
import torch
import transformers
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer


MODEL_NAME = "klue/roberta-base"
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_OUTPUT_DIR = BASE_DIR / "DL_models" / "roberta_tuning_best"


def load_frame(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"데이터 파일이 없습니다: {path}")
    frame = pd.read_csv(path)
    missing = {"question", "label"} - set(frame.columns)
    if missing:
        raise ValueError(f"{path}에 필요한 컬럼이 없습니다: {sorted(missing)}")
    if frame.empty or frame["label"].isna().any():
        raise ValueError(f"{path}의 데이터 또는 label이 비어 있습니다")
    frame = frame[["question", "label"]].copy()
    frame["question"] = frame["question"].fillna("").astype(str)
    frame["label"] = frame["label"].astype(str)
    if frame["label"].str.strip().eq("").any():
        raise ValueError(f"{path}에 빈 label이 있습니다")
    return frame


def encode_labels(frame: pd.DataFrame, label_to_id: dict[str, int]) -> np.ndarray:
    unknown = sorted(set(frame["label"]) - set(label_to_id))
    if unknown:
        raise ValueError(f"학습 데이터에 없는 label이 있습니다: {unknown}")
    return frame["label"].map(label_to_id).to_numpy(dtype=np.int64)


class EncodedDataset(Dataset):
    def __init__(self, encodings: dict[str, Any], labels: np.ndarray):
        self.encodings = encodings
        self.labels = torch.as_tensor(labels, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        item = {
            key: torch.tensor(values[index], dtype=torch.long)
            for key, values in self.encodings.items()
        }
        item["labels"] = self.labels[index]
        return item


def make_dataset(tokenizer: Any, frame: pd.DataFrame, labels: np.ndarray, max_length: int) -> EncodedDataset:
    encodings = tokenizer(
        frame["question"].tolist(),
        padding="max_length",
        truncation=True,
        max_length=max_length,
    )
    return EncodedDataset(encodings, labels)


def evaluate(
    model: torch.nn.Module, loader: DataLoader, device: torch.device
) -> tuple[np.ndarray, float, np.ndarray]:
    model.eval()
    predictions: list[int] = []
    confidences: list[float] = []
    loss_total = 0.0
    sample_count = 0
    with torch.inference_mode():
        for batch in loader:
            inputs = {key: value.to(device) for key, value in batch.items()}
            outputs = model(**inputs)
            batch_size = inputs["labels"].size(0)
            loss_total += outputs.loss.item() * batch_size
            sample_count += batch_size
            probabilities = torch.softmax(outputs.logits, dim=1)
            batch_confidences, batch_predictions = probabilities.max(dim=1)
            predictions.extend(batch_predictions.cpu().tolist())
            confidences.extend(batch_confidences.cpu().tolist())
    return (
        np.asarray(predictions, dtype=np.int64),
        loss_total / sample_count,
        np.asarray(confidences, dtype=np.float64),
    )


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--learning-rates", type=float, nargs="+",
                        default=[1e-5, 2e-5, 3e-5])
    parser.add_argument("--batch-sizes", type=int, nargs="+", default=[16, 32])
    parser.add_argument("--weight-decays", type=float, nargs="+",
                        default=[0.0, 0.01])
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--eval-batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main() -> None:
    run_start = time.perf_counter()
    started_at_utc = datetime.now(timezone.utc).isoformat()
    parser = build_parser()
    args = parser.parse_args()
    if args.epochs < 1 or args.max_length < 1 or args.eval_batch_size < 1:
        parser.error("epochs, max-length, eval-batch-size는 1 이상이어야 합니다")
    if any(value <= 0 for value in args.learning_rates):
        parser.error("learning-rates는 양수여야 합니다")
    if any(value < 1 for value in args.batch_sizes):
        parser.error("batch-sizes는 1 이상이어야 합니다")
    if any(value < 0 for value in args.weight_decays):
        parser.error("weight-decays는 0 이상이어야 합니다")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error(f"결과 폴더가 비어 있지 않습니다. 새 --output-dir를 지정하세요: {args.output_dir}")

    train_df = load_frame(args.data_dir / "train.csv")
    test_df = load_frame(args.data_dir / "test.csv")
    val_df = load_frame(args.data_dir / "val.csv")
    labels = [str(label) for label in sorted(train_df["label"].unique())]
    if len(labels) < 2:
        raise ValueError("분류에는 두 개 이상의 학습 label이 필요합니다")
    label_to_id = {label: index for index, label in enumerate(labels)}
    id_to_label = {index: label for label, index in label_to_id.items()}
    train_labels = encode_labels(train_df, label_to_id)
    test_labels = encode_labels(test_df, label_to_id)
    val_labels = encode_labels(val_df, label_to_id)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_seed(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    train_dataset = make_dataset(tokenizer, train_df, train_labels, args.max_length)
    test_dataset = make_dataset(tokenizer, test_df, test_labels, args.max_length)
    val_dataset = make_dataset(tokenizer, val_df, val_labels, args.max_length)
    train_eval_loader = DataLoader(train_dataset, batch_size=args.eval_batch_size)
    test_loader = DataLoader(test_dataset, batch_size=args.eval_batch_size)
    val_loader = DataLoader(val_dataset, batch_size=args.eval_batch_size)

    candidates = list(itertools.product(args.learning_rates, args.batch_sizes, args.weight_decays))
    print(f"모델: {MODEL_NAME} / 디바이스: {device} / 후보: {len(candidates)}개")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_dir = args.output_dir / "klue_roberta"
    history_path = args.output_dir / "tuning_history.csv"
    run_config = {
        "status": "running",
        "started_at_utc": started_at_utc,
        "model_name": MODEL_NAME,
        "device": str(device),
        "selection_metric": "val_macro_f1",
        "selection_tie_rule": "first_reached",
        "learning_rates": args.learning_rates,
        "batch_sizes": args.batch_sizes,
        "weight_decays": args.weight_decays,
        "epochs": args.epochs,
        "max_length": args.max_length,
        "eval_batch_size": args.eval_batch_size,
        "seed": args.seed,
        "labels": labels,
        "data": {
            name: {
                "samples": len(frame),
                "sha256": hashlib.sha256((args.data_dir / f"{name}.csv").read_bytes()).hexdigest(),
            }
            for name, frame in (("train", train_df), ("test", test_df), ("val", val_df))
        },
        "versions": {
            "python": sys.version.split()[0],
            "torch": str(torch.__version__),
            "transformers": transformers.__version__,
            "sklearn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (args.output_dir / "run_config.json").write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    best_val_f1 = -1.0
    best_config: dict[str, int | float | str] = {}
    best_val_predictions: np.ndarray | None = None
    best_val_confidences: np.ndarray | None = None
    best_val_loss = 0.0
    history: list[dict[str, int | float]] = []

    for trial_id, (learning_rate, batch_size, weight_decay) in enumerate(candidates, start=1):
        # 각 후보를 같은 사전학습 모델과 seed에서 시작해 공정하게 비교한다.
        set_seed(args.seed)
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_NAME,
            num_labels=len(labels),
            id2label=id_to_label,
            label2id=label_to_id,
        ).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

        for epoch in range(1, args.epochs + 1):
            epoch_start = time.perf_counter()
            model.train()
            train_loss_total = 0.0
            for batch in train_loader:
                batch = {key: value.to(device) for key, value in batch.items()}
                optimizer.zero_grad()
                loss = model(**batch).loss
                loss.backward()
                optimizer.step()
                train_loss_total += loss.item() * batch["labels"].size(0)

            train_loss = train_loss_total / len(train_dataset)
            train_predictions, train_eval_loss, _ = evaluate(model, train_eval_loader, device)
            train_accuracy = float(accuracy_score(train_labels, train_predictions))
            train_macro_f1 = float(f1_score(train_labels, train_predictions, average="macro", zero_division=0))
            test_predictions, test_loss, _ = evaluate(model, test_loader, device)
            test_accuracy = float(accuracy_score(test_labels, test_predictions))
            test_macro_f1 = float(f1_score(test_labels, test_predictions, average="macro", zero_division=0))
            val_predictions, val_loss, val_confidences = evaluate(model, val_loader, device)
            val_accuracy = float(accuracy_score(val_labels, val_predictions))
            val_macro_f1 = float(f1_score(val_labels, val_predictions, average="macro", zero_division=0))
            selection_updated = val_macro_f1 > best_val_f1
            if selection_updated:
                best_val_f1 = val_macro_f1
                best_val_predictions = val_predictions.copy()
                best_val_confidences = val_confidences.copy()
                best_val_loss = val_loss
                best_config = {
                    "model_name": MODEL_NAME,
                    "trial": trial_id,
                    "epoch": epoch,
                    "learning_rate": learning_rate,
                    "batch_size": batch_size,
                    "weight_decay": weight_decay,
                    "max_length": args.max_length,
                    "seed": args.seed,
                    "train_loss": train_loss,
                    "train_eval_loss": train_eval_loss,
                    "train_accuracy": train_accuracy,
                    "train_macro_f1": train_macro_f1,
                    "test_loss": test_loss,
                    "test_accuracy": test_accuracy,
                    "test_macro_f1": test_macro_f1,
                    "val_loss": val_loss,
                    "val_accuracy": val_accuracy,
                    "val_macro_f1": val_macro_f1,
                }
                model.save_pretrained(model_dir, safe_serialization=True)
                tokenizer.save_pretrained(model_dir)
                (args.output_dir / "best_config.json").write_text(
                    json.dumps(best_config, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            history.append({
                "trial": trial_id,
                "epoch": epoch,
                "learning_rate": learning_rate,
                "batch_size": batch_size,
                "weight_decay": weight_decay,
                "train_loss": train_loss,
                "train_eval_loss": train_eval_loss,
                "train_accuracy": train_accuracy,
                "train_macro_f1": train_macro_f1,
                "test_loss": test_loss,
                "test_accuracy": test_accuracy,
                "test_macro_f1": test_macro_f1,
                "val_loss": val_loss,
                "val_accuracy": val_accuracy,
                "val_macro_f1": val_macro_f1,
                "selection_updated": selection_updated,
                "epoch_seconds": time.perf_counter() - epoch_start,
            })
            pd.DataFrame(history).to_csv(history_path, index=False, encoding="utf-8-sig")
            print(
                f"후보 {trial_id}/{len(candidates)}, epoch {epoch}/{args.epochs}: "
                f"train loss={train_loss:.4f}, accuracy={train_accuracy:.4f}, Macro F1={train_macro_f1:.4f}; "
                f"test loss={test_loss:.4f}, accuracy={test_accuracy:.4f}, Macro F1={test_macro_f1:.4f}; "
                f"val loss={val_loss:.4f}, accuracy={val_accuracy:.4f}, Macro F1={val_macro_f1:.4f}"
            )

        del model, optimizer, train_loader
        gc.collect()
        if device.type == "cuda":
            torch.cuda.empty_cache()

    # 선택 시점에 기록한 예측으로 상세 결과를 만든다.
    if best_val_predictions is None or best_val_confidences is None:
        raise RuntimeError("선택된 학습 결과가 없습니다")
    val_metrics = {
        "model_name": MODEL_NAME,
        "dataset": "val.csv",
        "selection_metric": "val_macro_f1",
        "samples": len(val_df),
        "selected_trial": best_config["trial"],
        "selected_epoch": best_config["epoch"],
        "loss": best_val_loss,
        "accuracy": float(accuracy_score(val_labels, best_val_predictions)),
        "macro_f1": float(f1_score(val_labels, best_val_predictions, average="macro", zero_division=0)),
    }
    class_precision, class_recall, class_f1, class_support = precision_recall_fscore_support(
        val_labels, best_val_predictions, labels=list(range(len(labels))), zero_division=0
    )
    pd.DataFrame({
        "label": labels,
        "precision": class_precision,
        "recall": class_recall,
        "f1": class_f1,
        "support": class_support,
    }).to_csv(args.output_dir / "val_class_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        confusion_matrix(val_labels, best_val_predictions, labels=list(range(len(labels)))),
        index=labels,
        columns=labels,
    ).to_csv(args.output_dir / "val_confusion_matrix.csv", index_label="actual_label", encoding="utf-8-sig")
    pd.DataFrame({
        "row_number": np.arange(1, len(val_df) + 1),
        "true_label": [id_to_label[int(label)] for label in val_labels],
        "predicted_label": [id_to_label[int(label)] for label in best_val_predictions],
        "predicted_confidence": best_val_confidences,
        "is_correct": val_labels == best_val_predictions,
    }).to_csv(args.output_dir / "val_predictions.csv", index=False, encoding="utf-8-sig")

    model_file = args.output_dir / "klue_roberta_full_model.pt"
    saved_model = AutoModelForSequenceClassification.from_pretrained(model_dir).cpu()
    torch.save(saved_model, model_file)

    (args.output_dir / "val_metrics.json").write_text(
        json.dumps(val_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "label_map.json").write_text(
        json.dumps({"label_to_id": label_to_id, "id_to_label": id_to_label}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    run_config["status"] = "complete"
    run_config["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    run_config["duration_seconds"] = time.perf_counter() - run_start
    (args.output_dir / "run_config.json").write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"최적 val Macro F1: {best_val_f1:.4f}; 저장 모델 val 정확도: {val_metrics['accuracy']:.4f}")
    print(f"전체 모델 객체: {model_file}")
    print(f"토크나이저와 가중치 폴더: {model_dir}")
    print(f"평가 기록 폴더: {args.output_dir}")


if __name__ == "__main__":
    main()
