import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.tcm_extractor_schema import normalize_extraction_payload


def main() -> None:
    args = parse_args()
    evaluate(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate local TCM KG extraction model.")
    parser.add_argument("--model-name", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--adapter-path", default="models/tcm_extractor_lora")
    parser.add_argument("--eval-file", default="data/extraction/eval.jsonl")
    parser.add_argument("--output-dir", default="models/tcm_extractor_lora")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-new-tokens", type=int, default=2048)
    return parser.parse_args()


def evaluate(args: argparse.Namespace) -> None:
    from common.local_extractor import LocalTCMExtractor

    extractor = LocalTCMExtractor(model_name=args.model_name, adapter_path=args.adapter_path)
    rows = read_jsonl(Path(args.eval_file))[: args.limit]

    predictions = []
    json_ok = 0
    entity_scores = []
    relation_scores = []

    for row in rows:
        expected = normalize_extraction_payload(row["messages"][2]["content"])
        user_content = row["messages"][1]["content"]
        try:
            predicted_raw = extractor.extract(user_content, max_new_tokens=args.max_new_tokens)
            predicted = normalize_extraction_payload(predicted_raw)
            json_ok += 1
        except Exception:
            predicted = {"entities": [], "relations": []}

        entity_score = f1_score(entity_set(expected), entity_set(predicted))
        relation_score = f1_score(relation_set(expected), relation_set(predicted))
        entity_scores.append(entity_score)
        relation_scores.append(relation_score)
        predictions.append(
            {
                "id": row.get("id"),
                "expected": expected,
                "predicted": predicted,
                "entity_f1": entity_score,
                "relation_f1": relation_score,
            }
        )

    report = {
        "samples": len(rows),
        "json_parse_rate": json_ok / len(rows) if rows else 0,
        "entity_f1": sum(entity_scores) / len(entity_scores) if entity_scores else 0,
        "relation_f1": sum(relation_scores) / len(relation_scores) if relation_scores else 0,
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "sample_predictions.json").write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def entity_set(payload: Dict[str, Any]) -> Set[Tuple[str, str]]:
    return {(item["name"], item["type"]) for item in payload.get("entities", [])}


def relation_set(payload: Dict[str, Any]) -> Set[Tuple[str, str, str, str, str]]:
    return {
        (item["subject"], item["subject_type"], item["relation"], item["object"], item["object_type"])
        for item in payload.get("relations", [])
    }


def f1_score(expected: Set[Tuple[Any, ...]], predicted: Set[Tuple[Any, ...]]) -> float:
    if not expected and not predicted:
        return 1.0
    if not expected or not predicted:
        return 0.0
    true_positive = len(expected & predicted)
    precision = true_positive / len(predicted)
    recall = true_positive / len(expected)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


if __name__ == "__main__":
    main()
