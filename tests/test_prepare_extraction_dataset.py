import json
from pathlib import Path

from __007__training.prepare_extraction_dataset import prepare_rows, split_rows


def test_prepare_rows_writes_chat_messages_and_normalized_output(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            [
                {
                    "instruction": "请抽取",
                    "input": "【方剂名称】麻黄汤",
                    "output": json.dumps(
                        {
                            "entities": [{"name": "麻黄汤", "type": "Formula"}],
                            "relations": [
                                {
                                    "subject": "麻黄汤",
                                    "subject_type": "Formula",
                                    "relation": "HAS_INGRED",
                                    "object": "麻黄",
                                    "object_type": "Herb",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = prepare_rows([source])

    assert rows[0]["messages"][0]["role"] == "system"
    assert rows[0]["messages"][1]["role"] == "user"
    assert rows[0]["messages"][2]["role"] == "assistant"
    assistant_payload = json.loads(rows[0]["messages"][2]["content"])
    assert assistant_payload["entities"][0]["name"] == "麻黄汤"
    assert assistant_payload["relations"][0]["relation"] == "HAS_INGREDIENT"


def test_split_rows_is_deterministic_and_keeps_eval_sample():
    rows = [{"id": str(i), "messages": []} for i in range(20)]

    train_a, eval_a = split_rows(rows, eval_ratio=0.1, seed=42)
    train_b, eval_b = split_rows(rows, eval_ratio=0.1, seed=42)

    assert train_a == train_b
    assert eval_a == eval_b
    assert len(train_a) == 18
    assert len(eval_a) == 2
