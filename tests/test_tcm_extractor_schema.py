import json

from common.tcm_extractor_schema import (
    ALLOWED_ENTITY_TYPES,
    ALLOWED_RELATION_TYPES,
    normalize_extraction_payload,
)


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


def test_removes_empty_attributes_and_invalid_entities():
    payload = {
        "entities": [
            {
                "name": "麻黄汤",
                "type": "Formula",
                "attributes": {"effect": "发汗解表", "taboo": "", "usage": None},
            },
            {"name": "", "type": "Herb"},
            {"name": "未知类型", "type": "Unknown"},
        ],
        "relations": [],
    }

    result = normalize_extraction_payload(payload)

    assert result["entities"] == [
        {
            "name": "麻黄汤",
            "type": "Formula",
            "attributes": {"effect": "发汗解表"},
        }
    ]


def test_all_allowed_types_match_project_schema():
    assert ALLOWED_ENTITY_TYPES == {
        "Symptom",
        "Disease",
        "Formula",
        "Herb",
        "Effect",
        "Source",
    }
    assert ALLOWED_RELATION_TYPES == {
        "TREATS_DISEASE",
        "ALLEVIATES_SYMPTOM",
        "HAS_EFFECT",
        "HAS_INGREDIENT",
        "HAS_SYMPTOM",
        "FROM_SOURCE",
    }
