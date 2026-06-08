import json
from types import SimpleNamespace

from __007__training import evaluate_extractor


def test_evaluate_records_invalid_model_output_as_empty_prediction(monkeypatch, tmp_path):
    eval_file = tmp_path / "eval.jsonl"
    output_dir = tmp_path / "out"
    eval_file.write_text(
        json.dumps(
            {
                "id": "sample-1",
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "麻黄汤由麻黄、桂枝组成。"},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "entities": [{"name": "麻黄汤", "type": "Formula"}],
                                "relations": [],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    class BrokenExtractor:
        def __init__(self, model_name, adapter_path):
            pass

        def extract(self, text, max_new_tokens=2048):
            raise ValueError("invalid json")

    monkeypatch.setattr("common.local_extractor.LocalTCMExtractor", BrokenExtractor)

    evaluate_extractor.evaluate(
        SimpleNamespace(
            model_name="tiny",
            adapter_path="adapter",
            eval_file=str(eval_file),
            output_dir=str(output_dir),
            limit=1,
            max_new_tokens=8,
        )
    )

    report = json.loads((output_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert report["samples"] == 1
    assert report["json_parse_rate"] == 0
    assert report["entity_f1"] == 0
