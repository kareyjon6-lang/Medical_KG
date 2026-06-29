import pytest

from __005__fastapi.app.services.cypher_guard import CypherGuardError, ensure_read_only_cypher
from __005__fastapi.app.services.graph_service import build_knowledge_graph
from __005__fastapi.app.services.search_service import build_search_results


def test_read_only_guard_accepts_parameterized_match_query():
    query = """
    MATCH (n)
    WHERE n.name CONTAINS $query
    RETURN n
    LIMIT $limit
    """

    assert ensure_read_only_cypher(query) == "MATCH (n) WHERE n.name CONTAINS $query RETURN n LIMIT $limit"


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (n) DETACH DELETE n",
        "CREATE (n:Herb {name: 'x'}) RETURN n",
        "CALL dbms.components()",
        "MATCH (n) RETURN n; MATCH (m) RETURN m",
    ],
)
def test_read_only_guard_rejects_write_or_multi_statement_queries(query):
    with pytest.raises(CypherGuardError):
        ensure_read_only_cypher(query)


class FakeNeo4j:
    def __init__(self, records=None):
        self.records = records or []
        self.calls = []

    def run_cypher(self, query, parameters=None):
        self.calls.append((query, parameters or {}))
        return self.records


def test_search_results_use_parameters_and_public_node_shape():
    fake = FakeNeo4j(
        [
            {
                "node": {
                    "name": "麻黄汤",
                    "label": "Formula",
                    "source": "伤寒论",
                    "ingredients": "麻黄、桂枝、杏仁、甘草",
                }
            }
        ]
    )

    results = build_search_results(fake, "麻黄", limit=5)

    assert fake.calls[0][1] == {"query": "麻黄", "labels": "", "source": "", "effects": "", "limit": 5}
    assert results == [
        {
            "id": "Formula:麻黄汤",
            "name": "麻黄汤",
            "label": "Formula",
            "properties": {
                "ingredients": "麻黄、桂枝、杏仁、甘草",
                "source": "伤寒论",
            },
        }
    ]


def test_empty_search_returns_named_entities_without_filtering():
    fake = FakeNeo4j(
        [
            {
                "node": {
                    "name": "桂枝汤",
                    "label": "Formula",
                    "source": "伤寒论",
                }
            }
        ]
    )

    results = build_search_results(fake, "", limit=20)

    query, parameters = fake.calls[0]
    assert "$query = ''" in query
    assert parameters == {"query": "", "labels": "", "source": "", "effects": "", "limit": 20}
    assert results[0]["name"] == "桂枝汤"


def test_search_results_can_filter_by_label():
    fake = FakeNeo4j([])

    build_search_results(fake, "", limit=20, label="Formula")

    query, parameters = fake.calls[0]
    assert "$labels = '' OR any(item IN split($labels, ',') WHERE item IN labels(n) OR coalesce(n.label, '') = item)" in query
    assert parameters == {"query": "", "labels": "Formula", "source": "", "effects": "", "limit": 20}


def test_search_results_accept_disease_and_symptom_labels():
    fake = FakeNeo4j([])

    build_search_results(fake, "", limit=20, label="Disease,Symptom")

    query, parameters = fake.calls[0]
    assert "any(item IN split($labels, ',')" in query
    assert parameters == {"query": "", "labels": "Disease,Symptom", "source": "", "effects": "", "limit": 20}


def test_disease_and_symptom_search_ignore_formula_filters():
    fake = FakeNeo4j([])

    build_search_results(fake, "", limit=20, label="Disease", source="伤寒论", effects=["发汗解表"])

    assert fake.calls[0][1] == {"query": "", "labels": "Disease", "source": "", "effects": "", "limit": 20}


def test_search_results_can_filter_by_source_and_effects():
    fake = FakeNeo4j([])

    build_search_results(fake, "", limit=20, label="Formula,Herb", source="伤寒论", effects=["发汗解表", "宣肺平喘"])

    query, parameters = fake.calls[0]
    assert "$source = '' OR node_source CONTAINS toLower($source)" in query
    assert "size(effect_filters) = 0 OR all(effect IN effect_filters" in query
    assert parameters == {
        "query": "",
        "labels": "Formula,Herb",
        "source": "伤寒论",
        "effects": "发汗解表|宣肺平喘",
        "limit": 20,
    }


def test_search_results_raise_limit_cap_to_three_thousand():
    fake = FakeNeo4j([])

    build_search_results(fake, "", limit=3000)

    assert fake.calls[0][1]["limit"] == 3000


def test_search_results_summarize_related_entities():
    fake = FakeNeo4j(
        [
            {
                "properties": {"name": "麻黄汤"},
                "label": "Formula",
                "related_items": [
                    {
                        "type": "HAS_INGREDIENT",
                        "label": "Herb",
                        "properties": {"name": "麻黄"},
                    },
                    {
                        "type": "ALLEVIATES_SYMPTOM",
                        "label": "Symptom",
                        "properties": {"name": "恶寒发热"},
                    },
                ],
            }
        ]
    )

    results = build_search_results(fake, "麻黄汤", limit=5)

    assert results[0]["properties"]["related"] == "组成：麻黄（药材）；缓解症状：恶寒发热（症状）"


def test_search_results_repair_mojibake_names_and_properties():
    fake = FakeNeo4j(
        [
            {
                "properties": {
                    "name": "éº»é»æ±¤",
                    "effect": "åæ±è§£è¡¨",
                },
                "label": "Formula",
                "related_items": [
                    {
                        "type": "HAS_INGREDIENT",
                        "label": "Herb",
                        "properties": {"name": "éº»é»"},
                    }
                ],
            }
        ]
    )

    results = build_search_results(fake, "麻黄汤", limit=5)

    assert results[0]["name"] == "麻黄汤"
    assert results[0]["properties"]["effect"] == "发汗解表"
    assert results[0]["properties"]["related"] == "组成：麻黄（药材）"


def test_graph_builder_deduplicates_nodes_and_edges_for_frontend():
    fake = FakeNeo4j(
        [
            {
                "source": {"name": "麻黄汤", "label": "Formula"},
                "target": {"name": "麻黄", "label": "Herb", "effect": "发汗解表"},
                "rel_type": "HAS_INGREDIENT",
            },
            {
                "source": {"name": "麻黄汤", "label": "Formula"},
                "target": {"name": "麻黄", "label": "Herb", "effect": "发汗解表"},
                "rel_type": "HAS_INGREDIENT",
            },
        ]
    )

    graph = build_knowledge_graph(fake, "麻黄汤", depth=1, limit=20)

    assert fake.calls[0][1] == {"query": "麻黄汤"}
    assert fake.calls[1][1] == {"query": "麻黄汤", "depth": 1, "limit": 20}
    assert graph["nodes"] == [
        {"id": "Formula:麻黄汤", "name": "麻黄汤", "label": "Formula", "properties": {}},
        {
            "id": "Herb:麻黄",
            "name": "麻黄",
            "label": "Herb",
            "properties": {"effect": "发汗解表"},
        },
    ]
    assert graph["edges"] == [
        {
            "id": "Formula:麻黄汤-HAS_INGREDIENT-Herb:麻黄",
            "source": "Formula:麻黄汤",
            "target": "Herb:麻黄",
            "label": "HAS_INGREDIENT",
        }
    ]


def test_graph_builder_uses_two_hop_query_when_depth_is_two():
    fake = FakeNeo4j(
        [
            {
                "source": {"name": "麻黄汤", "label": "Formula"},
                "target": {"name": "麻黄", "label": "Herb"},
                "rel_type": "HAS_INGREDIENT",
            }
        ]
    )

    build_knowledge_graph(fake, "麻黄汤", depth=2, limit=20)

    query, parameters = fake.calls[1]
    assert parameters == {"query": "麻黄汤", "depth": 2, "limit": 20}
    assert "*1..2" in query


def test_graph_builder_falls_back_to_contains_only_when_exact_center_missing():
    class SequencedNeo4j:
        def __init__(self):
            self.calls = []

        def run_cypher(self, query, parameters=None):
            self.calls.append((query, parameters or {}))
            if len(self.calls) == 1:
                return []
            return [
                {
                    "source": {"name": "阿胶鸡子黄汤", "label": "Formula"},
                    "target": {"name": "阿胶", "label": "Herb"},
                    "rel_type": "HAS_INGREDIENT",
                }
            ]

    fake = SequencedNeo4j()
    graph = build_knowledge_graph(fake, "阿胶", depth=1, limit=20)

    assert fake.calls[0][1] == {"query": "阿胶"}
    assert "center.name = $query" not in fake.calls[1][0]
    assert "CONTAINS toLower($query)" in fake.calls[1][0]
    assert graph["nodes"][0]["name"] == "阿胶鸡子黄汤"


def test_graph_builder_keeps_real_two_hop_edges_instead_of_collapsing_to_center():
    fake = FakeNeo4j(
        [
            {
                "source": {"name": "阿魏", "label": "Herb"},
                "target": {"name": "阿魏化痞膏", "label": "Formula"},
                "rel_type": "HAS_INGREDIENT",
            },
            {
                "source": {"name": "阿魏化痞膏", "label": "Formula"},
                "target": {"name": "脘腹疼痛", "label": "Symptom"},
                "rel_type": "ALLEVIATES_SYMPTOM",
            },
        ]
    )

    graph = build_knowledge_graph(fake, "阿魏", depth=2, limit=20)

    assert {
        "id": "Herb:阿魏-HAS_INGREDIENT-Formula:阿魏化痞膏",
        "source": "Herb:阿魏",
        "target": "Formula:阿魏化痞膏",
        "label": "HAS_INGREDIENT",
    } in graph["edges"]
    assert {
        "id": "Formula:阿魏化痞膏-ALLEVIATES_SYMPTOM-Symptom:脘腹疼痛",
        "source": "Formula:阿魏化痞膏",
        "target": "Symptom:脘腹疼痛",
        "label": "ALLEVIATES_SYMPTOM",
    } in graph["edges"]
