# TCM KG Website Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Scheme 1 deployable TCM knowledge graph website and replace API-based KG extraction with a local fine-tuned extractor.

**Architecture:** Preserve the existing LangGraph/Neo4j/FAISS chain, wrap it in production-oriented FastAPI endpoints, add a Next.js frontend, and introduce a local Qwen LoRA extractor with shared schema validation. Figma and HyperFrames define the visual system before the frontend is polished.

**Tech Stack:** FastAPI, LangGraph, Neo4j, FAISS, Next.js, TypeScript, Tailwind CSS, Cytoscape.js or React Flow, PyTorch, Transformers, PEFT/LoRA, Qwen2.5-1.5B-Instruct, Figma, HyperFrames.

---

## File Structure

- Create `common/tcm_extractor_schema.py`: shared Pydantic schema, relation/type constants, JSON parsing, normalization.
- Create `common/local_extractor.py`: local model loader and inference wrapper.
- Create `__007__training/prepare_extraction_dataset.py`: normalize current instruction data into train/eval JSONL.
- Create `__007__training/train_extractor_lora.py`: train LoRA adapter.
- Create `__007__training/evaluate_extractor.py`: evaluate JSON parse rate, entity set F1, relation set F1.
- Create `__007__training/README.md`: training commands and expected artifacts.
- Modify `__002__extract_information/__000__extract_graph_data_utils.py`: allow local extractor backend.
- Create `__005__fastapi/app/`: production API package.
- Create `frontend/`: Next.js website.
- Create `design/DESIGN.md`: visual identity for Figma, HyperFrames, and frontend.
- Create `hyperframes-ui/`: motion concept composition.
- Create `requirements.txt`: backend and training dependencies.
- Create `.env.example`: safe environment template.

## Task 1: Data Schema And Normalization

**Files:**
- Create: `common/tcm_extractor_schema.py`
- Create: `tests/test_tcm_extractor_schema.py`

- [ ] **Step 1: Write failing schema tests**

```python
import json

from common.tcm_extractor_schema import normalize_extraction_payload


def test_normalizes_relation_typo_and_drops_blank_relation():
    payload = {
        "entities": [{"name": "麻黄汤", "type": "Formula"}],
        "relations": [
            {
                "subject": "麻黄汤",
                "subject_type": "Formula",
                "relation": "HAS_INGRED",
                "object": "麻黄",
                "object_type": "Herb",
            },
            {
                "subject": "麻黄汤",
                "subject_type": "Formula",
                "relation": "",
                "object": "桂枝",
                "object_type": "Herb",
            },
        ],
    }

    result = normalize_extraction_payload(json.dumps(payload, ensure_ascii=False))

    assert result["relations"] == [
        {
            "subject": "麻黄汤",
            "subject_type": "Formula",
            "relation": "HAS_INGREDIENT",
            "object": "麻黄",
            "object_type": "Herb",
        }
    ]
```

- [ ] **Step 2: Run test and verify RED**

Run: `python -m pytest tests/test_tcm_extractor_schema.py -v`

Expected: fails because `common.tcm_extractor_schema` does not exist.

- [ ] **Step 3: Implement schema normalization**

Create constants for allowed entity and relation types. Parse string/dict payloads, fix `HAS_INGRED` to `HAS_INGREDIENT`, remove invalid blank relations, remove empty attributes, and return a dict with `entities` and `relations`.

- [ ] **Step 4: Run test and verify GREEN**

Run: `python -m pytest tests/test_tcm_extractor_schema.py -v`

Expected: pass.

## Task 2: Dataset Preparation

**Files:**
- Create: `__007__training/prepare_extraction_dataset.py`
- Create: `tests/test_prepare_extraction_dataset.py`
- Create output directory at runtime: `data/extraction/`

- [ ] **Step 1: Write failing dataset preparation test**

```python
import json
from pathlib import Path

from __007__training.prepare_extraction_dataset import prepare_rows


def test_prepare_rows_writes_chat_messages_and_normalized_output(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps([
        {
            "instruction": "请抽取",
            "input": "【方剂名称】麻黄汤",
            "output": json.dumps({
                "entities": [{"name": "麻黄汤", "type": "Formula"}],
                "relations": []
            }, ensure_ascii=False),
        }
    ], ensure_ascii=False), encoding="utf-8")

    rows = prepare_rows([source])

    assert rows[0]["messages"][0]["role"] == "system"
    assert rows[0]["messages"][1]["role"] == "user"
    assert rows[0]["messages"][2]["role"] == "assistant"
    assert json.loads(rows[0]["messages"][2]["content"])["entities"][0]["name"] == "麻黄汤"
```

- [ ] **Step 2: Run test and verify RED**

Run: `python -m pytest tests/test_prepare_extraction_dataset.py -v`

Expected: fails because dataset module does not exist.

- [ ] **Step 3: Implement dataset preparation**

Implement CLI:

```bash
python __007__training/prepare_extraction_dataset.py \
  --input __002__extract_information/extract_formula_finetune_data.json \
  --input __002__extract_information/extract_herb_finetune_data.json \
  --output-dir data/extraction \
  --eval-ratio 0.1 \
  --seed 42
```

Outputs:

- `data/extraction/train.jsonl`
- `data/extraction/eval.jsonl`
- `data/extraction/dataset_report.json`

- [ ] **Step 4: Run test and verify GREEN**

Run: `python -m pytest tests/test_prepare_extraction_dataset.py -v`

Expected: pass.

## Task 3: Local Extractor Training

**Files:**
- Create: `__007__training/train_extractor_lora.py`
- Create: `__007__training/evaluate_extractor.py`
- Create: `__007__training/README.md`
- Modify: `requirements.txt`

- [ ] **Step 1: Add training dependencies**

Add compatible packages for Python 3.12 training environment:

```text
torch
transformers
datasets
accelerate
peft
sentencepiece
safetensors
pytest
```

- [ ] **Step 2: Install dependencies**

Run in the selected training environment:

```bash
python -m pip install -r requirements.txt
```

- [ ] **Step 3: Implement LoRA training CLI**

Use base model `Qwen/Qwen2.5-1.5B-Instruct`. Default arguments:

```bash
python __007__training/train_extractor_lora.py \
  --model-name Qwen/Qwen2.5-1.5B-Instruct \
  --train-file data/extraction/train.jsonl \
  --eval-file data/extraction/eval.jsonl \
  --output-dir models/tcm_extractor_lora \
  --max-length 4096 \
  --epochs 3 \
  --batch-size 1 \
  --gradient-accumulation-steps 8 \
  --learning-rate 2e-4
```

- [ ] **Step 4: Implement evaluation CLI**

Evaluate representative samples and save:

- `models/tcm_extractor_lora/eval_report.json`
- `models/tcm_extractor_lora/sample_predictions.json`

- [ ] **Step 5: Train adapter**

Run the training command. If GPU memory fails, reduce `max-length` to 3072 or 2048 and keep the report.

## Task 4: Local Extractor Inference Replacement

**Files:**
- Create: `common/local_extractor.py`
- Modify: `__002__extract_information/__000__extract_graph_data_utils.py`
- Test: `tests/test_local_extractor_backend_selection.py`

- [ ] **Step 1: Write failing backend-selection test**

```python
from __002__extract_information.__000__extract_graph_data_utils import get_extractor_backend_name


def test_prefers_local_extractor_when_adapter_path_is_set(monkeypatch):
    monkeypatch.setenv("TCM_EXTRACTOR_ADAPTER_PATH", "models/tcm_extractor_lora")

    assert get_extractor_backend_name() == "local"
```

- [ ] **Step 2: Run test and verify RED**

Run: `python -m pytest tests/test_local_extractor_backend_selection.py -v`

Expected: fails because helper does not exist.

- [ ] **Step 3: Implement local extractor wrapper**

Load tokenizer/model once, apply adapter when configured, generate JSON with deterministic decoding, and normalize via `common.tcm_extractor_schema`.

- [ ] **Step 4: Modify extraction utility**

Add backend selection:

- `TCM_EXTRACTOR_BACKEND=local`
- `TCM_EXTRACTOR_BACKEND=api`
- `auto`: local if adapter exists, otherwise API.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_tcm_extractor_schema.py tests/test_local_extractor_backend_selection.py -v`

Expected: pass.

## Task 5: Production FastAPI Package

**Files:**
- Create: `__005__fastapi/app/main.py`
- Create: `__005__fastapi/app/schemas.py`
- Create: `__005__fastapi/app/services/search_service.py`
- Create: `__005__fastapi/app/services/graph_service.py`
- Create: `__005__fastapi/app/services/cypher_guard.py`
- Test: `tests/test_cypher_guard.py`

- [ ] **Step 1: Write failing Cypher guard tests**

```python
from __005__fastapi.app.services.cypher_guard import assert_readonly_cypher


def test_rejects_write_cypher():
    try:
        assert_readonly_cypher("MATCH (n) DELETE n")
    except ValueError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_accepts_match_return_limit():
    assert_readonly_cypher("MATCH (n) RETURN n LIMIT 10")
```

- [ ] **Step 2: Run test and verify RED**

Run: `python -m pytest tests/test_cypher_guard.py -v`

Expected: fails because module does not exist.

- [ ] **Step 3: Implement API modules**

Endpoints:

- `GET /api/health`
- `POST /api/chat/stream`
- `GET /api/search`
- `GET /api/entities/{name}`
- `GET /api/graph`
- `POST /api/extract`

- [ ] **Step 4: Run backend tests**

Run: `python -m pytest tests/test_cypher_guard.py -v`

Expected: pass.

## Task 6: Next.js Frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/app/assistant/page.tsx`
- Create: `frontend/app/search/page.tsx`
- Create: `frontend/app/graph/page.tsx`
- Create: `frontend/app/architecture/page.tsx`
- Create: `frontend/components/`
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/session.ts`
- Create: `frontend/app/globals.css`

- [ ] **Step 1: Scaffold Next.js app**

Run in `frontend/` after files are created:

```bash
npm install
```

- [ ] **Step 2: Implement session helper**

Session helper creates and persists an anonymous id in local storage.

- [ ] **Step 3: Implement API client**

Use `NEXT_PUBLIC_API_BASE_URL`; never hardcode localhost in production code.

- [ ] **Step 4: Implement pages**

Assistant, Search, Graph Explorer, and Architecture pages use the visual identity from `design/DESIGN.md`.

- [ ] **Step 5: Verify frontend build**

Run:

```bash
npm run build
```

Expected: build succeeds.

## Task 7: Figma And HyperFrames Visual Design

**Files:**
- Create: `design/DESIGN.md`
- Create: `hyperframes-ui/DESIGN.md`
- Create: `hyperframes-ui/index.html`

- [ ] **Step 1: Create visual identity doc**

Define palette, typography, layout language, motion language, and anti-patterns.

- [ ] **Step 2: Create Figma file**

Use Figma tools to create:

- Assistant desktop.
- Search + graph desktop.
- Assistant mobile.
- Tokens/motion notes page.

- [ ] **Step 3: Create HyperFrames motion prototype**

Author a short composition demonstrating assistant reveal, herbarium background, and graph-link pulses.

- [ ] **Step 4: Validate HyperFrames**

Run:

```bash
npx hyperframes lint
npx hyperframes validate
npx hyperframes inspect
```

Expected: pass or only intentional/justified layout warnings.

## Task 8: Deployment Hygiene

**Files:**
- Create: `.env.example`
- Create: `DEPLOYMENT.md`
- Modify: `README.md`

- [ ] **Step 1: Add `.env.example`**

Include variable names without secrets.

- [ ] **Step 2: Remove committed secrets from future tracked files**

Do not include actual API keys or passwords in new files.

- [ ] **Step 3: Add deployment guide**

Document Vercel frontend, backend host, Neo4j Aura/VM, FAISS/model artifacts, and environment variables.

## Task 9: Final Verification

- [ ] Run backend tests.
- [ ] Run dataset preparation.
- [ ] Run extraction smoke test with local model or documented trained adapter.
- [ ] Run frontend build.
- [ ] Open the website locally and smoke-test Assistant, Search, and Graph pages.
- [ ] Verify Figma screenshots.
- [ ] Verify HyperFrames validation.
- [ ] Audit every acceptance criterion in `docs/superpowers/specs/2026-06-02-tcm-kg-website-design.md`.
