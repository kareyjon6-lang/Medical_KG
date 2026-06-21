from types import SimpleNamespace

import pytest

from __005__fastapi.app.services.knowledge_import_service import (
    FormulaNotFoundError,
    build_preview_graph,
    delete_formula_from_neo4j,
    extract_herb_knowledge,
    import_knowledge_to_neo4j,
    normalize_knowledge_payload,
    parse_document_text,
)


def test_parse_document_text_supports_text_and_rejects_doc():
    assert parse_document_text("艾叶.txt", "艾叶具有温经止血的功效。".encode("utf-8")) == "艾叶具有温经止血的功效。"

    with pytest.raises(ValueError, match="docx"):
        parse_document_text("旧文档.doc", b"binary")


def test_normalize_knowledge_payload_filters_relation_types():
    payload = normalize_knowledge_payload(
        {
            "herb": {"name": "艾叶", "effect": "温经止血"},
            "relations": [
                {"relation": "HAS_EFFECT", "object": "温经止血", "object_type": "Effect"},
                {"relation": "DELETE", "object": "危险", "object_type": "Effect"},
            ],
        }
    )

    assert payload["herb"]["name"] == "艾叶"
    assert payload["relations"] == [
        {
            "subject": "艾叶",
            "subject_type": "Herb",
            "relation": "HAS_EFFECT",
            "object": "温经止血",
            "object_type": "Effect",
        }
    ]


def test_extract_herb_knowledge_requires_herb_name():
    class FakeLlm:
        def invoke(self, _messages):
            return SimpleNamespace(content='{"herb":{"effect":"温经止血"},"relations":[]}')

    with pytest.raises(ValueError, match="药材名称"):
        extract_herb_knowledge("艾叶具有温经止血的功效。", llm=FakeLlm())


def test_extract_herb_knowledge_parses_structured_crawler_text_without_llm():
    class FailingLlm:
        def invoke(self, _messages):
            raise AssertionError("结构化栏目文本不应该依赖 LLM 才能抽取")

    payload = extract_herb_knowledge(
        """
        【中药名称】阿胶
        来源
        为马科动物驴的皮去毛后熬制而成的胶块。
        性味
        甘，平。
        功效
        滋阴润燥，补血，止血，安胎。
        主治
        治血虚，虚劳咳嗽，吐血，妇女月经不调。
        经脉
        入肺经、肝经、肾经。
        用法用量
        内服：烊化兑服，5~10g。
        注意禁忌
        脾胃虚弱、消化不良者慎服。
        """,
        llm=FailingLlm(),
    )

    assert payload["herb"]["name"] == "阿胶"
    assert payload["herb"]["property_flavor"] == "甘，平。"
    assert payload["herb"]["taboo"] == "脾胃虚弱、消化不良者慎服。"
    assert {"subject": "阿胶", "subject_type": "Herb", "relation": "HAS_EFFECT", "object": "补血", "object_type": "Effect"} in payload["relations"]
    assert {"subject": "阿胶", "subject_type": "Herb", "relation": "ALLEVIATES_SYMPTOM", "object": "虚劳咳嗽", "object_type": "Symptom"} in payload["relations"]


def test_extract_formula_document_builds_ingredient_graph_without_llm():
    class FailingLlm:
        def invoke(self, _messages):
            raise AssertionError("方剂栏目文本不应该依赖 LLM 才能识别")

    text = """
    【方剂名称】阿胶鸡子黄汤
    出处
    《通俗伤寒论》
    组成
    阿胶9克（烊化），鸡子黄（即鸡蛋黄）2枚（冲入）生地黄12克，生白芍12克，茯神木12克，炙甘草6克。
    功用
    养血滋阴，柔肝熄风。
    主治
    邪热久留，灼伤真阴，筋脉拘急，手足蠕动，或头目晕眩。
    用法
    水煎服。
    """

    payload = extract_herb_knowledge(text, llm=FailingLlm())
    graph = build_preview_graph(payload)

    assert payload["herb"]["name"] == "阿胶鸡子黄汤"
    assert payload["herb"]["label"] == "Formula"
    assert payload["herb"]["source"] == "《通俗伤寒论》"
    assert {"subject": "阿胶鸡子黄汤", "subject_type": "Formula", "relation": "HAS_INGREDIENT", "object": "阿胶", "object_type": "Herb"} in payload["relations"]
    assert {"subject": "阿胶鸡子黄汤", "subject_type": "Formula", "relation": "HAS_INGREDIENT", "object": "生地黄", "object_type": "Herb"} in payload["relations"]
    assert {"subject": "阿胶鸡子黄汤", "subject_type": "Formula", "relation": "HAS_EFFECT", "object": "柔肝熄风", "object_type": "Effect"} in payload["relations"]
    assert {"subject": "阿胶鸡子黄汤", "subject_type": "Formula", "relation": "FROM_SOURCE", "object": "通俗伤寒论", "object_type": "Source"} in payload["relations"]
    assert [relation["object"] for relation in payload["relations"] if relation["relation"] == "FROM_SOURCE"] == ["通俗伤寒论"]
    assert len(payload["relations"]) >= 8
    assert any(node["name"] == "阿胶鸡子黄汤" and node["label"] == "Formula" for node in graph["nodes"])
    assert any(edge["label"] == "HAS_INGREDIENT" for edge in graph["edges"])


def test_extract_real_formula_style_text_keeps_rich_relationships_without_llm():
    class FailingLlm:
        def invoke(self, _messages):
            raise AssertionError("真实方剂栏目文本不应该退化为只识别一条关系")

    text = """
    【方剂名称】阿胶鸡子黄汤
    - 中医百科
    - 阿胶鸡子黄汤
    阿胶鸡子黄汤　的药方
    出处
    《通俗伤寒论》
    组成
    阿胶9克（烊化），鸡子黄（即鸡蛋黄）2枚（冲入）生地黄12克，生白芍12克，茯神木12克，炙甘草6克，生石决明15克，生牡蛎15克，钩藤9克，络石藤15克。
    功用
    养血滋阴，柔肝熄风。
    主治
    邪热久留，灼伤真阴，筋脉拘急，手足蠕动，或头目晕眩，舌绛苔少，脉细而数等证。
    用法
    水煎服。
    """

    payload = extract_herb_knowledge(text, llm=FailingLlm())
    relations = payload["relations"]

    assert payload["herb"]["name"] == "阿胶鸡子黄汤"
    assert payload["herb"]["label"] == "Formula"
    assert sum(1 for relation in relations if relation["relation"] == "HAS_INGREDIENT") >= 10
    assert sum(1 for relation in relations if relation["relation"] == "HAS_EFFECT") >= 2
    assert sum(1 for relation in relations if relation["relation"] == "ALLEVIATES_SYMPTOM") >= 6
    assert [relation["object"] for relation in relations if relation["relation"] == "FROM_SOURCE"] == ["通俗伤寒论"]


def test_build_preview_graph_preserves_non_center_subject_relationships():
    graph = build_preview_graph(
        {
            "herb": {"name": "阿胶鸡子黄汤", "label": "Formula"},
            "relations": [
                {"subject": "阿胶鸡子黄汤", "subject_type": "Formula", "relation": "HAS_INGREDIENT", "object": "阿胶", "object_type": "Herb"},
                {"subject": "阿胶", "subject_type": "Herb", "relation": "HAS_EFFECT", "object": "补血", "object_type": "Effect"},
            ],
        }
    )

    assert any(node["id"] == "Formula:阿胶鸡子黄汤" for node in graph["nodes"])
    assert any(node["id"] == "Herb:阿胶" for node in graph["nodes"])
    assert any(edge["id"] == "Formula:阿胶鸡子黄汤-HAS_INGREDIENT-Herb:阿胶" for edge in graph["edges"])
    assert any(edge["id"] == "Herb:阿胶-HAS_EFFECT-Effect:补血" for edge in graph["edges"])


def test_delete_formula_from_neo4j_uses_exact_formula_or_herb_match(monkeypatch):
    class FakeNeo4j:
        def __init__(self):
            self.deleted = False

        def run_cypher(self, query, parameters=None):
            if "RETURN n.name AS name" in query:
                return [{"name": "阿胶", "labels": ["Herb"]}]
            if "DETACH DELETE" in query:
                self.deleted = True
                return [{"deleted": 1}]
            return []

        def get_all_node_names(self, label=None):
            return ["阿胶", "麻黄汤"]

        def export_tcm_metadata_to_json(self, output_path="tcm_metadata.json"):
            return output_path

    monkeypatch.setattr("__005__fastapi.app.services.knowledge_import_service.refresh_graph_metadata", lambda _client: None)
    monkeypatch.setattr("__005__fastapi.app.services.knowledge_import_service.remove_entities_from_runtime_index", lambda _names: 1)
    fake = FakeNeo4j()
    result = delete_formula_from_neo4j(fake, "阿胶")

    assert fake.deleted is True
    assert result["deleted"] == 1
    assert result["name"] == "阿胶"
    assert result["index_refresh"] == "masked"


def test_delete_formula_from_neo4j_reports_missing_with_suggestions(monkeypatch):
    class FakeNeo4j:
        def run_cypher(self, _query, parameters=None):
            return []

        def get_all_node_names(self, label=None):
            return ["阿胶", "阿胶鸡子黄汤", "麻黄汤"]

    monkeypatch.setattr("__005__fastapi.app.services.knowledge_import_service.refresh_graph_metadata", lambda _client: None)
    monkeypatch.setattr("__005__fastapi.app.services.knowledge_import_service.remove_entities_from_runtime_index", lambda _names: 0)

    with pytest.raises(FormulaNotFoundError) as exc_info:
        delete_formula_from_neo4j(FakeNeo4j(), "阿胶鸡")

    assert "未在知识图谱中找到方药" in str(exc_info.value)
    assert "阿胶鸡子黄汤" in exc_info.value.suggestions


def test_import_knowledge_updates_runtime_index_incrementally(monkeypatch):
    class FakeNeo4j:
        def __init__(self):
            self.queries = []

        def run_multiple_cypher(self, queries):
            self.queries = queries

    refreshed = []
    appended = []
    monkeypatch.setattr("__005__fastapi.app.services.knowledge_import_service.refresh_graph_metadata", lambda client: refreshed.append(client))
    monkeypatch.setattr("__005__fastapi.app.services.knowledge_import_service.append_entities_to_runtime_index", lambda names: appended.extend(names) or 3)

    fake = FakeNeo4j()
    result = import_knowledge_to_neo4j(
        fake,
        {
            "herb": {"name": "阿胶鸡子黄汤", "label": "Formula"},
            "relations": [
                {"relation": "HAS_INGREDIENT", "object": "阿胶", "object_type": "Herb"},
                {"relation": "HAS_EFFECT", "object": "养血滋阴", "object_type": "Effect"},
            ],
        },
    )

    assert result["index_refresh"] == "incremental"
    assert result["index_added"] == 3
    assert len(fake.queries) == 5
    assert refreshed == [fake]
    assert {"阿胶鸡子黄汤", "阿胶", "养血滋阴"}.issubset(set(appended))
