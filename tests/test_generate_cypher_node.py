from __004__langgraph_more_nodes.nodes.generate_neo4j_cypher_node import (
    build_fallback_cypher_queries,
    extract_cypher_queries,
)


def test_extract_cypher_queries_accepts_fenced_json():
    raw = """
    ```json
    {"cypher": [{"query": "MATCH (s:Symptom {name: '脚疼'}) RETURN s"}]}
    ```
    """

    queries = extract_cypher_queries(raw)

    assert queries == ["MATCH (s:Symptom {name: '脚疼'}) RETURN s"]


def test_build_fallback_cypher_queries_uses_extracted_symptom():
    queries = build_fallback_cypher_queries({"user_input_symptoms": ["脚疼"]})

    assert len(queries) == 1
    assert "'脚疼'" in queries[0]
    assert "OPTIONAL MATCH" in queries[0]
