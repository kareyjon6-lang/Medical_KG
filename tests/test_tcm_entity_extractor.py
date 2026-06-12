from common.tcm_entity_extractor import (
    ENTITY_TYPES,
    build_char_bio_tags,
    entities_to_state_fields,
    empty_entity_result,
    extract_tcm_entities,
    find_lexicon_entities,
    merge_entity_results,
    merge_token_predictions,
)


def test_build_char_bio_tags_prefers_longer_entities_and_labels_repeated_mentions():
    text = "麻黄汤含麻黄和桂枝，麻黄可发汗。"
    entities = [
        {"name": "麻黄", "type": "Herb"},
        {"name": "麻黄汤", "type": "Formula"},
        {"name": "桂枝", "type": "Herb"},
        {"name": "发汗", "type": "Effect"},
    ]

    tags = build_char_bio_tags(text, entities)

    assert tags[:3] == ["B-Formula", "I-Formula", "I-Formula"]
    assert tags[4:6] == ["B-Herb", "I-Herb"]
    assert tags[10:12] == ["B-Herb", "I-Herb"]
    assert tags[13:15] == ["B-Effect", "I-Effect"]


def test_merge_token_predictions_returns_project_entity_shape():
    text = "银翘散适合风热感冒，可用金银花。"
    offsets = [(0, 1), (1, 2), (2, 3), (5, 7), (7, 9), (12, 13), (13, 14), (14, 15)]
    labels = [
        "B-Formula",
        "I-Formula",
        "I-Formula",
        "B-Disease",
        "I-Disease",
        "B-Herb",
        "I-Herb",
        "I-Herb",
    ]

    result = merge_token_predictions(text, offsets, labels)

    assert result == {
        "symptoms": [],
        "diseases": ["风热感冒"],
        "formulas": ["银翘散"],
        "herbs": ["金银花"],
        "effects": [],
        "sources": [],
    }


def test_entities_to_state_fields_keeps_all_expected_keys():
    entities = {"formulas": ["银翘散"], "herbs": ["金银花"]}

    state_fields = entities_to_state_fields(entities)

    assert set(ENTITY_TYPES) == {"Symptom", "Disease", "Formula", "Herb", "Effect", "Source"}
    assert state_fields["user_input_formulas"] == ["银翘散"]
    assert state_fields["user_input_herbs"] == ["金银花"]
    assert state_fields["user_input_symptoms"] == []
    assert state_fields["user_input_sources"] == []


def test_find_lexicon_entities_prefers_full_names_and_merges_with_model_output():
    text = "银翘散可以治疗风热感冒吗？能不能加金银花？"
    lexicon = {
        "Formula": ["银翘散", "银翘"],
        "Disease": ["风热感冒"],
        "Herb": ["金银花"],
    }
    model_result = {
        "symptoms": [],
        "diseases": [],
        "formulas": ["散"],
        "herbs": ["银翘"],
        "effects": [],
        "sources": [],
    }

    lexicon_result = find_lexicon_entities(text, lexicon)
    merged = merge_entity_results(lexicon_result, model_result, text=text)

    assert lexicon_result["formulas"] == ["银翘散"]
    assert lexicon_result["diseases"] == ["风热感冒"]
    assert lexicon_result["herbs"] == ["金银花"]
    assert merged["formulas"] == ["银翘散"]


def test_merge_entity_results_keeps_substring_entity_when_it_appears_separately():
    text = "麻黄汤里面有麻黄和桂枝吗？"
    lexicon_result = {
        "symptoms": [],
        "diseases": [],
        "formulas": ["麻黄汤"],
        "herbs": ["麻黄", "桂枝"],
        "effects": [],
        "sources": [],
    }

    merged = merge_entity_results(lexicon_result, text=text)

    assert merged["formulas"] == ["麻黄汤"]
    assert merged["herbs"] == ["麻黄", "桂枝"]


def test_common_symptom_fallback_extracts_short_pain_phrase(monkeypatch):
    class FakeExtractor:
        def extract(self, text):
            return empty_entity_result()

    monkeypatch.setattr("common.tcm_entity_extractor.get_default_extractor", lambda: FakeExtractor())

    result = extract_tcm_entities("你好，我脚疼")

    assert "脚疼" in result["symptoms"]
