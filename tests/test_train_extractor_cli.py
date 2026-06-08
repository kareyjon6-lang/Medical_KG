import sys

from __007__training import train_extractor_lora


def test_training_cli_accepts_smoke_test_limits(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_extractor_lora.py",
            "--max-train-samples",
            "2",
            "--max-eval-samples",
            "1",
            "--max-steps",
            "1",
            "--device-map",
            "cpu",
        ],
    )

    args = train_extractor_lora.parse_args()

    assert args.max_train_samples == 2
    assert args.max_eval_samples == 1
    assert args.max_steps == 1
    assert args.device_map == "cpu"
