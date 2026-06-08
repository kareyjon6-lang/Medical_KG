import json
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Set


ALLOWED_ENTITY_TYPES: Set[str] = {
    "Symptom",
    "Disease",
    "Formula",
    "Herb",
    "Effect",
    "Source",
}

ALLOWED_RELATION_TYPES: Set[str] = {
    "TREATS_DISEASE",
    "ALLEVIATES_SYMPTOM",
    "HAS_EFFECT",
    "HAS_INGREDIENT",
    "HAS_SYMPTOM",
    "FROM_SOURCE",
}

RELATION_ALIASES = {
    "HAS_INGRED": "HAS_INGREDIENT",
}


def parse_extraction_json(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    if not isinstance(payload, str):
        raise TypeError("Extraction payload must be a JSON string or mapping.")

    text = payload.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])

    if not isinstance(parsed, Mapping):
        raise ValueError("Extraction JSON must decode to an object.")
    return dict(parsed)


def normalize_extraction_payload(payload: Any) -> Dict[str, List[Dict[str, Any]]]:
    parsed = parse_extraction_json(payload)
    return {
        "entities": normalize_entities(parsed.get("entities", [])),
        "relations": normalize_relations(parsed.get("relations", [])),
    }


def normalize_entities(entities: Any) -> List[Dict[str, Any]]:
    if not isinstance(entities, list):
        return []

    normalized: List[Dict[str, Any]] = []
    seen = set()
    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        name = _clean_text(entity.get("name"))
        entity_type = _clean_text(entity.get("type"))
        if not name or entity_type not in ALLOWED_ENTITY_TYPES:
            continue

        item: Dict[str, Any] = {"name": name, "type": entity_type}
        attributes = _normalize_attributes(entity.get("attributes"))
        if attributes:
            item["attributes"] = attributes

        key = (item["name"], item["type"], json.dumps(item.get("attributes", {}), ensure_ascii=False, sort_keys=True))
        if key not in seen:
            normalized.append(item)
            seen.add(key)

    return normalized


def normalize_relations(relations: Any) -> List[Dict[str, str]]:
    if not isinstance(relations, list):
        return []

    normalized: List[Dict[str, str]] = []
    seen = set()
    for relation in relations:
        if not isinstance(relation, Mapping):
            continue

        item = {
            "subject": _clean_text(relation.get("subject")),
            "subject_type": _clean_text(relation.get("subject_type")),
            "relation": _normalize_relation_type(relation.get("relation")),
            "object": _clean_text(relation.get("object")),
            "object_type": _clean_text(relation.get("object_type")),
        }

        if not _is_valid_relation(item):
            continue

        key = (item["subject"], item["subject_type"], item["relation"], item["object"], item["object_type"])
        if key not in seen:
            normalized.append(item)
            seen.add(key)

    return normalized


def dumps_normalized_payload(payload: Any, indent: Optional[int] = None) -> str:
    normalized = normalize_extraction_payload(payload)
    return json.dumps(normalized, ensure_ascii=False, indent=indent)


def _normalize_attributes(attributes: Any) -> Dict[str, Any]:
    if not isinstance(attributes, Mapping):
        return {}

    normalized: Dict[str, Any] = {}
    for key, value in attributes.items():
        clean_key = _clean_text(key)
        if not clean_key or value is None:
            continue
        if isinstance(value, str):
            clean_value = _clean_text(value)
            if not clean_value:
                continue
            normalized[clean_key] = clean_value
        else:
            normalized[clean_key] = value
    return normalized


def _normalize_relation_type(value: Any) -> str:
    relation_type = _clean_text(value)
    return RELATION_ALIASES.get(relation_type, relation_type)


def _is_valid_relation(relation: Mapping[str, str]) -> bool:
    return (
        bool(relation["subject"])
        and bool(relation["object"])
        and relation["subject_type"] in ALLOWED_ENTITY_TYPES
        and relation["object_type"] in ALLOWED_ENTITY_TYPES
        and relation["relation"] in ALLOWED_RELATION_TYPES
    )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
