from typing import Any, Dict, List


ENTITY_TYPE_TO_RUNTIME_KEY = {
    "Symptom": "symptoms",
    "Disease": "diseases",
    "Formula": "formulas",
    "Herb": "herbs",
    "Effect": "effects",
    "Source": "sources",
}


EMPTY_RUNTIME_ENTITIES = {
    "symptoms": [],
    "diseases": [],
    "formulas": [],
    "herbs": [],
    "effects": [],
    "sources": [],
}


def empty_runtime_entities() -> Dict[str, List[str]]:
    return {key: list(value) for key, value in EMPTY_RUNTIME_ENTITIES.items()}


def runtime_entities_from_local_payload(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    entities = empty_runtime_entities()
    seen = {key: set() for key in EMPTY_RUNTIME_ENTITIES}

    for item in payload.get("entities", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        runtime_key = ENTITY_TYPE_TO_RUNTIME_KEY.get(item.get("type"))
        if not name or not runtime_key or name in seen[runtime_key]:
            continue
        entities[runtime_key].append(name)
        seen[runtime_key].add(name)

    return entities
