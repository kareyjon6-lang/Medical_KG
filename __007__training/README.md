# Local TCM KG Extractor Training

This folder trains a local structured extraction model to replace the API-based extraction path used by the original data extraction utility.

## Base Model

Default base: `Qwen/Qwen2.5-1.5B-Instruct`.

Why this base:

- Strong Chinese instruction following.
- Small enough for LoRA training on the local RTX 4060 Laptop 8GB.
- Official Qwen2.5 model card emphasizes structured outputs and JSON robustness.
- The current dataset is already instruction-to-JSON, so a causal instruction model is a natural fit.

## Prepare Dataset

```powershell
python __007__training\prepare_extraction_dataset.py `
  --input __002__extract_information\extract_formula_finetune_data.json `
  --input __002__extract_information\extract_herb_finetune_data.json `
  --output-dir data\extraction `
  --eval-ratio 0.1 `
  --seed 42
```

Expected outputs:

- `data/extraction/train.jsonl`
- `data/extraction/eval.jsonl`
- `data/extraction/dataset_report.json`

## Training Environment

Use a separate Python 3.12 virtual environment if possible.

```powershell
python -m venv .venv-training
.\.venv-training\Scripts\python.exe -m pip install --upgrade pip
.\.venv-training\Scripts\python.exe -m pip install -r requirements-training.txt
```

If CUDA wheels are not picked automatically on Windows, install PyTorch from the official selector for the local driver/CUDA combination, then install the remaining requirements.

For this workspace, CUDA PyTorch downloads repeatedly timed out, while the CPU wheel installed successfully:

```powershell
.\.venv-training\Scripts\python.exe -m pip install torch==2.11.0+cpu --index-url https://download.pytorch.org/whl/cpu
.\.venv-training\Scripts\python.exe -m pip install -r requirements-training.txt
```

CPU mode is useful for smoke tests. It is not recommended for full Qwen2.5-1.5B LoRA training.

## Train LoRA Adapter

```powershell
python __007__training\train_extractor_lora.py `
  --model-name Qwen/Qwen2.5-1.5B-Instruct `
  --train-file data\extraction\train.jsonl `
  --eval-file data\extraction\eval.jsonl `
  --output-dir models\tcm_extractor_lora `
  --max-length 4096 `
  --epochs 3 `
  --batch-size 1 `
  --gradient-accumulation-steps 8 `
  --learning-rate 2e-4 `
  --device-map auto
```

If the GPU runs out of memory, reduce `--max-length` to `3072` or `2048` and keep the chosen value in the evaluation report.

## Smoke Test

This command verifies dataset loading, tokenization, LoRA adapter creation, saving, and evaluation plumbing without claiming model quality:

```powershell
.\.venv-training\Scripts\python.exe __007__training\train_extractor_lora.py `
  --model-name tiny-random/qwen2.5 `
  --output-dir models\tcm_extractor_lora_smoke `
  --max-train-samples 2 `
  --max-eval-samples 1 `
  --max-steps 1 `
  --max-length 256 `
  --batch-size 1 `
  --gradient-accumulation-steps 1 `
  --device-map cpu

.\.venv-training\Scripts\python.exe __007__training\evaluate_extractor.py `
  --model-name tiny-random/qwen2.5 `
  --adapter-path models\tcm_extractor_lora_smoke `
  --output-dir models\tcm_extractor_lora_smoke `
  --limit 1 `
  --max-new-tokens 64
```

## Evaluate

```powershell
python __007__training\evaluate_extractor.py `
  --model-name Qwen/Qwen2.5-1.5B-Instruct `
  --adapter-path models\tcm_extractor_lora `
  --eval-file data\extraction\eval.jsonl `
  --output-dir models\tcm_extractor_lora `
  --limit 50
```

Expected outputs:

- `models/tcm_extractor_lora/eval_report.json`
- `models/tcm_extractor_lora/sample_predictions.json`
