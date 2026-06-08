from common.runtime_entity_extractor import runtime_entities_from_local_payload


def test_runtime_entities_from_local_payload_maps_schema_to_state_lists():
    payload = {
        "entities": [
            {"name": "恶寒发热", "type": "Symptom"},
            {"name": "感冒", "type": "Disease"},
            {"name": "麻黄汤", "type": "Formula"},
            {"name": "麻黄", "type": "Herb"},
            {"name": "发汗解表", "type": "Effect"},
            {"name": "伤寒论", "type": "Source"},
            {"name": "麻黄", "type": "Herb"},
        ],
        "relations": [],
    }

    entities = runtime_entities_from_local_payload(payload)

    assert entities == {
        "symptoms": ["恶寒发热"],
        "diseases": ["感冒"],
        "formulas": ["麻黄汤"],
        "herbs": ["麻黄"],
        "effects": ["发汗解表"],
        "sources": ["伤寒论"],
    }
