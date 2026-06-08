import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.tcm_extractor_schema import normalize_extraction_payload


SYSTEM_PROMPT = """你是一个中医知识图谱结构化抽取模型。请从输入文本中抽取实体和关系，并只输出严格 JSON。
实体类型只能是：Symptom, Disease, Formula, Herb, Effect, Source。
关系类型只能是：TREATS_DISEASE, ALLEVIATES_SYMPTOM, HAS_EFFECT, HAS_INGREDIENT, HAS_SYMPTOM, FROM_SOURCE。
输出格式必须是 {"entities": [...], "relations": [...]}，不要输出解释、Markdown 或额外文本。"""


def prepare_rows(input_paths: Sequence[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for input_path in input_paths:
        raw_rows = _load_instruction_rows(input_path)
        for index, item in enumerate(raw_rows):
            source_text = str(item.get("input", "")).strip()
            if not source_text:
                continue

            normalized_output = normalize_extraction_payload(item.get("output", "{}"))
            assistant_content = json.dumps(normalized_output, ensure_ascii=False, separators=(",", ":"))
            row_id = "{}:{}".format(input_path.name, index)
            rows.append(
                {
                    "id": row_id,
                    "source_file": input_path.name,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": _build_user_message(item, source_text)},
                        {"role": "assistant", "content": assistant_content},
                    ],
                }
            )
    return rows


def split_rows(rows: Sequence[Dict[str, Any]], eval_ratio: float, seed: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not rows:
        return [], []
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    eval_size = max(1, int(round(len(shuffled) * eval_ratio))) if len(shuffled) > 1 else 0
    eval_rows = shuffled[:eval_size]
    train_rows = shuffled[eval_size:]
    return train_rows, eval_rows


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_report(path: Path, train_rows: Sequence[Dict[str, Any]], eval_rows: Sequence[Dict[str, Any]]) -> None:
    report = {
        "train_samples": len(train_rows),
        "eval_samples": len(eval_rows),
        "total_samples": len(train_rows) + len(eval_rows),
    }
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare TCM extraction fine-tuning dataset.")
    parser.add_argument("--input", action="append", required=True, help="Input fine-tuning JSON file. Can be repeated.")
    parser.add_argument("--output-dir", default="data/extraction")
    parser.add_argument("--eval-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_paths = [Path(value) for value in args.input]
    output_dir = Path(args.output_dir)
    rows = prepare_rows(input_paths)
    train_rows, eval_rows = split_rows(rows, eval_ratio=args.eval_ratio, seed=args.seed)

    write_jsonl(output_dir / "train.jsonl", train_rows)
    write_jsonl(output_dir / "eval.jsonl", eval_rows)
    write_report(output_dir / "dataset_report.json", train_rows, eval_rows)
    print("Prepared {} train samples and {} eval samples.".format(len(train_rows), len(eval_rows)))


def _load_instruction_rows(input_path: Path) -> List[Dict[str, Any]]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("data", "rows", "results", "out_list"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("Unsupported fine-tuning data format: {}".format(input_path))


def _build_user_message(item: Dict[str, Any], source_text: str) -> str:
    instruction = str(item.get("instruction", "请从以下中医文本中抽取知识图谱结构，包括实体与关系。")).strip()
    return "{}\n\n输入文本：\n{}".format(instruction, source_text)


if __name__ == "__main__":
    main()
