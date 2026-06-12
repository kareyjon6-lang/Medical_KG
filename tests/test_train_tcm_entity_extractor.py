from types import SimpleNamespace

from scripts.train_tcm_entity_extractor import build_training_argument_kwargs


def test_make_training_arguments_loads_best_model_by_validation_f1():
    args = SimpleNamespace(
        output_dir="models/tcm_entity_extractor",
        epochs=8.0,
        batch_size=8,
        learning_rate=3e-5,
        seed=42,
        early_stopping_patience=2,
    )

    kwargs = build_training_argument_kwargs(args)

    assert kwargs["load_best_model_at_end"] is True
    assert kwargs["metric_for_best_model"] == "eval_entity_f1"
    assert kwargs["greater_is_better"] is True
    assert kwargs["save_strategy"] == "epoch"
