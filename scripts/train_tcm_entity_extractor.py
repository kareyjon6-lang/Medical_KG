import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

# 该脚本用于训练本地中医实体抽取模型，服务于知识入库与问答识别。
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.tcm_entity_extractor import ENTITY_TYPES, build_char_bio_tags


LABELS = ["O"] + [f"{prefix}-{entity_type}" for entity_type in ENTITY_TYPES for prefix in ("B", "I")]
LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}
ID_TO_LABEL = {index: label for label, index in LABEL_TO_ID.items()}


class TCMTokenDataset(Dataset):
    def __init__(self, features: Sequence[Dict[str, Any]]):
        self.features = list(features)

    def __len__(self) -> int:
        return len(self.features)

    def __getitem__(self, index: int) -> Dict[str, torch.Tensor]:
        return {key: torch.tensor(value) for key, value in self.features[index].items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the local TCM entity extractor.")
    parser.add_argument(
        "--formula-data",
        default=str(ROOT_DIR / "__002__extract_information" / "extract_formula_finetune_data.json"),
    )
    parser.add_argument(
        "--herb-data",
        default=str(ROOT_DIR / "__002__extract_information" / "extract_herb_finetune_data.json"),
    )
    parser.add_argument("--base-model", default=str(ROOT_DIR / "bert-base-chinese"))
    parser.add_argument("--output-dir", default=str(ROOT_DIR / "models" / "tcm_entity_extractor"))
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--epochs", type=float, default=8.0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--eval-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--early-stopping-patience", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0, help="Limit examples for smoke tests. 0 means all data.")
    return parser.parse_args()


def load_rows(paths: Sequence[str], limit: int = 0) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        rows.extend(data)
    if limit > 0:
        return rows[:limit]
    return rows


def output_to_entities(output: str) -> List[Dict[str, str]]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return []

    entities = []
    for entity in payload.get("entities", []):
        name = str(entity.get("name") or "").strip()
        entity_type = str(entity.get("type") or "").strip()
        if name and entity_type in ENTITY_TYPES:
            entities.append({"name": name, "type": entity_type})
    return entities


def tokenize_and_align_labels(row: Dict[str, Any], tokenizer: Any, max_length: int) -> Dict[str, List[int]]:
    text = str(row.get("input") or "")
    entities = output_to_entities(str(row.get("output") or ""))
    char_tags = build_char_bio_tags(text, entities)

    encoded = tokenizer(
        text,
        truncation=True,
        max_length=max_length,
        return_offsets_mapping=True,
    )
    labels: List[int] = []
    for start, end in encoded.pop("offset_mapping"):
        if start == end:
            labels.append(-100)
        elif start < len(char_tags):
            labels.append(LABEL_TO_ID.get(char_tags[start], LABEL_TO_ID["O"]))
        else:
            labels.append(LABEL_TO_ID["O"])

    encoded["labels"] = labels
    return encoded


def build_features(rows: Sequence[Dict[str, Any]], tokenizer: Any, max_length: int) -> List[Dict[str, List[int]]]:
    return [tokenize_and_align_labels(row, tokenizer, max_length) for row in rows if row.get("input")]


def build_entity_lexicon(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    lexicon = {entity_type: set() for entity_type in ENTITY_TYPES}
    for row in rows:
        for entity in output_to_entities(str(row.get("output") or "")):
            lexicon[entity["type"]].add(entity["name"])
    return {
        entity_type: sorted(names, key=lambda name: (len(name), name), reverse=True)
        for entity_type, names in lexicon.items()
    }


def split_features(
    features: Sequence[Dict[str, List[int]]],
    eval_ratio: float,
    seed: int,
) -> tuple[List[Dict[str, List[int]]], List[Dict[str, List[int]]]]:
    shuffled = list(features)
    random.Random(seed).shuffle(shuffled)
    eval_size = max(1, int(len(shuffled) * eval_ratio)) if len(shuffled) > 1 else 0
    return shuffled[eval_size:], shuffled[:eval_size]


def compute_token_metrics(eval_pred: Any) -> Dict[str, float]:
    predictions, labels = eval_pred
    prediction_ids = np.argmax(predictions, axis=-1)
    true_positive = 0
    false_positive = 0
    false_negative = 0

    for predicted_row, label_row in zip(prediction_ids, labels):
        for predicted_id, label_id in zip(predicted_row, label_row):
            if label_id == -100:
                continue
            predicted_is_entity = int(predicted_id) != LABEL_TO_ID["O"]
            label_is_entity = int(label_id) != LABEL_TO_ID["O"]
            if predicted_is_entity and label_is_entity and int(predicted_id) == int(label_id):
                true_positive += 1
            elif predicted_is_entity and not label_is_entity:
                false_positive += 1
            elif not predicted_is_entity and label_is_entity:
                false_negative += 1
            elif predicted_is_entity and label_is_entity and int(predicted_id) != int(label_id):
                false_positive += 1
                false_negative += 1

    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    return {"entity_precision": precision, "entity_recall": recall, "entity_f1": f1}


def build_training_argument_kwargs(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "output_dir": args.output_dir,
        "num_train_epochs": args.epochs,
        "per_device_train_batch_size": args.batch_size,
        "per_device_eval_batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "weight_decay": 0.01,
        "logging_steps": 20,
        "save_strategy": "epoch",
        "save_total_limit": 3,
        "seed": args.seed,
        "report_to": [],
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_entity_f1",
        "greater_is_better": True,
    }


def make_training_arguments(args: argparse.Namespace) -> TrainingArguments:
    kwargs = build_training_argument_kwargs(args)
    try:
        return TrainingArguments(evaluation_strategy="epoch", **kwargs)
    except TypeError:
        return TrainingArguments(eval_strategy="epoch", **kwargs)


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    rows = load_rows([args.formula_data, args.herb_data], limit=args.limit)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)
    features = build_features(rows, tokenizer, args.max_length)
    train_features, eval_features = split_features(features, args.eval_ratio, args.seed)

    model = AutoModelForTokenClassification.from_pretrained(
        args.base_model,
        num_labels=len(LABELS),
        id2label=ID_TO_LABEL,
        label2id=LABEL_TO_ID,
    )

    callbacks = []
    if eval_features and args.early_stopping_patience > 0:
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=args.early_stopping_patience))

    trainer = Trainer(
        model=model,
        args=make_training_arguments(args),
        train_dataset=TCMTokenDataset(train_features),
        eval_dataset=TCMTokenDataset(eval_features),
        tokenizer=tokenizer,
        data_collator=DataCollatorForTokenClassification(tokenizer),
        compute_metrics=compute_token_metrics,
        callbacks=callbacks,
    )
    trainer.train()
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    metrics = trainer.evaluate() if eval_features else {}
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metrics_path = output_path / "eval_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as file:
        json.dump(metrics, file, ensure_ascii=False, indent=2)

    summary_path = output_path / "training_summary.json"
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(
            {
                "requested_epochs": args.epochs,
                "early_stopping_patience": args.early_stopping_patience,
                "best_metric_name": "eval_entity_f1",
                "best_metric_value": trainer.state.best_metric,
                "best_model_checkpoint": trainer.state.best_model_checkpoint,
                "global_step": trainer.state.global_step,
                "final_epoch": trainer.state.epoch,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    lexicon_path = output_path / "entity_lexicon.json"
    with open(lexicon_path, "w", encoding="utf-8") as file:
        json.dump(build_entity_lexicon(rows), file, ensure_ascii=False, indent=2)

    print(f"Saved TCM entity extractor to {args.output_dir}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
