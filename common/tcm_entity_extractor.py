import os
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from common.path_utils import get_file_path


ENTITY_TYPES = ("Symptom", "Disease", "Formula", "Herb", "Effect", "Source")

ENTITY_TO_OUTPUT_KEY = {
    "Symptom": "symptoms",
    "Disease": "diseases",
    "Formula": "formulas",
    "Herb": "herbs",
    "Effect": "effects",
    "Source": "sources",
}

OUTPUT_TO_STATE_KEY = {
    "symptoms": "user_input_symptoms",
    "diseases": "user_input_diseases",
    "formulas": "user_input_formulas",
    "herbs": "user_input_herbs",
    "effects": "user_input_effects",
    "sources": "user_input_sources",
}


def empty_entity_result() -> Dict[str, List[str]]:
    return {key: [] for key in ENTITY_TO_OUTPUT_KEY.values()}


def build_char_bio_tags(text: str, entities: Iterable[Dict[str, Any]]) -> List[str]:
    tags = ["O"] * len(text)
    spans: List[Tuple[int, int, str]] = []

    for entity in entities:
        name = str(entity.get("name") or "").strip()
        entity_type = str(entity.get("type") or "").strip()
        if not name or entity_type not in ENTITY_TYPES:
            continue

        start = text.find(name)
        while start != -1:
            spans.append((start, start + len(name), entity_type))
            start = text.find(name, start + 1)

    occupied = [False] * len(text)
    for start, end, entity_type in sorted(spans, key=lambda item: (item[1] - item[0], -item[0]), reverse=True):
        if start < 0 or end > len(text) or any(occupied[start:end]):
            continue
        tags[start] = f"B-{entity_type}"
        for index in range(start + 1, end):
            tags[index] = f"I-{entity_type}"
        for index in range(start, end):
            occupied[index] = True

    return tags


def merge_token_predictions(
    text: str,
    offsets: Sequence[Tuple[int, int]],
    labels: Sequence[str],
) -> Dict[str, List[str]]:
    result = empty_entity_result()
    current_type: Optional[str] = None
    current_start: Optional[int] = None
    current_end: Optional[int] = None

    def flush() -> None:
        nonlocal current_type, current_start, current_end
        if current_type and current_start is not None and current_end is not None:
            value = text[current_start:current_end].strip()
            key = ENTITY_TO_OUTPUT_KEY.get(current_type)
            if value and key and value not in result[key]:
                result[key].append(value)
        current_type = None
        current_start = None
        current_end = None

    for offset, label in zip(offsets, labels):
        start, end = int(offset[0]), int(offset[1])
        if start == end or start < 0 or end > len(text) or label == "O":
            flush()
            continue

        if "-" not in label:
            flush()
            continue

        prefix, entity_type = label.split("-", 1)
        if entity_type not in ENTITY_TYPES:
            flush()
            continue

        if prefix == "B" or current_type != entity_type or current_end != start:
            flush()
            current_type = entity_type
            current_start = start
            current_end = end
        elif prefix == "I":
            current_end = end
        else:
            flush()

    flush()
    return result


def entities_to_state_fields(entities: Dict[str, List[str]]) -> Dict[str, List[str]]:
    return {state_key: list(entities.get(output_key, [])) for output_key, state_key in OUTPUT_TO_STATE_KEY.items()}


def find_lexicon_entities(text: str, lexicon: Dict[str, Sequence[str]]) -> Dict[str, List[str]]:
    result = empty_entity_result()
    occupied = [False] * len(text)
    candidates: List[Tuple[int, int, str, str]] = []

    for entity_type, names in lexicon.items():
        if entity_type not in ENTITY_TYPES:
            continue
        for raw_name in names:
            name = str(raw_name or "").strip()
            if not name:
                continue
            start = text.find(name)
            while start != -1:
                candidates.append((start, start + len(name), entity_type, name))
                start = text.find(name, start + 1)

    for start, end, entity_type, name in sorted(candidates, key=lambda item: (item[1] - item[0], -item[0]), reverse=True):
        if start < 0 or end > len(text) or any(occupied[start:end]):
            continue
        key = ENTITY_TO_OUTPUT_KEY[entity_type]
        if name not in result[key]:
            result[key].append(name)
        for index in range(start, end):
            occupied[index] = True

    return result


def merge_entity_results(*results: Dict[str, List[str]], text: Optional[str] = None) -> Dict[str, List[str]]:
    merged = empty_entity_result()
    accepted: List[str] = []

    for result in results:
        for key in merged:
            for value in result.get(key, []):
                entity = str(value or "").strip()
                if not entity:
                    continue
                if any(entity == existing for existing in accepted):
                    continue
                if any(_is_only_covered_substring(entity, existing, accepted, text) for existing in accepted):
                    continue
                merged[key].append(entity)
                accepted.append(entity)

    return merged


COMMON_SYMPTOM_PATTERNS = (
    "头疼",
    "头痛",
    "脑袋疼",
    "脚疼",
    "脚痛",
    "腰疼",
    "腰痛",
    "腹痛",
    "肚子疼",
    "胃疼",
    "胃痛",
    "咳嗽",
    "发热",
    "发烧",
    "喉咙痛",
    "咽喉痛",
)


def find_common_symptom_entities(text: str) -> Dict[str, List[str]]:
    result = empty_entity_result()
    for symptom in COMMON_SYMPTOM_PATTERNS:
        if symptom in text and symptom not in result["symptoms"]:
            result["symptoms"].append(symptom)
    return result


def _is_only_covered_substring(
    entity: str,
    existing: str,
    accepted: Sequence[str],
    text: Optional[str],
) -> bool:
    if entity not in existing or entity == existing:
        return False
    if not text:
        return True

    covered_spans: List[Tuple[int, int]] = []
    for accepted_entity in accepted:
        start = text.find(accepted_entity)
        while start != -1:
            covered_spans.append((start, start + len(accepted_entity)))
            start = text.find(accepted_entity, start + 1)

    start = text.find(entity)
    while start != -1:
        end = start + len(entity)
        if not any(span_start <= start and end <= span_end for span_start, span_end in covered_spans):
            return False
        start = text.find(entity, start + 1)
    return True


@dataclass
class LocalTCMEntityExtractor:
    model_path: Optional[str] = None
    device: Optional[str] = None
    max_length: int = 256

    def __post_init__(self) -> None:
        self.model_path = self.model_path or os.getenv(
            "TCM_EXTRACTOR_MODEL_PATH",
            get_file_path("models/tcm_entity_extractor_best"),
        )
        self.device = self.device or os.getenv("TCM_EXTRACTOR_DEVICE")
        if self.device and self.device.lower() == "auto":
            self.device = None
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._lexicon: Optional[Dict[str, List[str]]] = None
        self._load_error: Optional[Exception] = None

    @property
    def is_available(self) -> bool:
        return self._ensure_loaded()

    @property
    def load_error(self) -> Optional[Exception]:
        return self._load_error

    def extract(self, text: str) -> Dict[str, List[str]]:
        if not text:
            return empty_entity_result()

        lexicon_result = find_lexicon_entities(text, self._load_lexicon())
        if not self._ensure_loaded():
            return lexicon_result

        encoded = self._tokenizer(
            text,
            return_offsets_mapping=True,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_length,
        )
        offsets = encoded.pop("offset_mapping")[0].tolist()
        encoded = {key: value.to(self._model.device) for key, value in encoded.items()}

        with self._torch.no_grad():
            logits = self._model(**encoded).logits[0]
            prediction_ids = logits.argmax(dim=-1).detach().cpu().tolist()

        id2label = {int(key): value for key, value in self._model.config.id2label.items()}
        labels = [id2label.get(index, "O") for index in prediction_ids]
        model_result = merge_token_predictions(text, offsets, labels)
        return merge_entity_results(lexicon_result, model_result, text=text)

    def _load_lexicon(self) -> Dict[str, List[str]]:
        if self._lexicon is not None:
            return self._lexicon

        self._lexicon = {}
        if not self.model_path:
            return self._lexicon

        lexicon_path = os.path.join(self.model_path, "entity_lexicon.json")
        if not os.path.isfile(lexicon_path):
            return self._lexicon

        try:
            with open(lexicon_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            self._lexicon = {
                entity_type: sorted({str(name).strip() for name in names if str(name).strip()}, key=len, reverse=True)
                for entity_type, names in payload.items()
                if entity_type in ENTITY_TYPES and isinstance(names, list)
            }
        except Exception:
            self._lexicon = {}
        return self._lexicon

    def _ensure_loaded(self) -> bool:
        if self._model is not None and self._tokenizer is not None:
            return True
        if self._load_error is not None:
            return False
        if not self.model_path or not os.path.isdir(self.model_path):
            self._load_error = FileNotFoundError(f"TCM extractor model not found: {self.model_path}")
            return False

        try:
            import torch
            from transformers import AutoModelForTokenClassification, AutoTokenizer

            self._torch = torch
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_path, use_fast=True)
            self._model = AutoModelForTokenClassification.from_pretrained(self.model_path)
            if not self.device:
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model.to(self.device)
            self._model.eval()
            return True
        except Exception as exc:
            self._load_error = exc
            self._tokenizer = None
            self._model = None
            return False


_DEFAULT_EXTRACTOR: Optional[LocalTCMEntityExtractor] = None


def get_default_extractor() -> LocalTCMEntityExtractor:
    global _DEFAULT_EXTRACTOR
    if _DEFAULT_EXTRACTOR is None:
        _DEFAULT_EXTRACTOR = LocalTCMEntityExtractor()
    return _DEFAULT_EXTRACTOR


def extract_tcm_entities(text: str) -> Dict[str, List[str]]:
    clean_text = text or ""
    extractor_result = get_default_extractor().extract(clean_text)
    common_symptoms = find_common_symptom_entities(clean_text)
    return merge_entity_results(extractor_result, common_symptoms, text=clean_text)
