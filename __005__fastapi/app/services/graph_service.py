from __005__fastapi.app.services.cypher_guard import ensure_read_only_cypher
from __005__fastapi.app.services.search_service import node_to_public_node


EXACT_CENTER_QUERY = ensure_read_only_cypher(
    """
    MATCH (center)
    WHERE center.name = $query
    RETURN 1 AS found
    LIMIT 1
    """
)

GRAPH_QUERY_EXACT = ensure_read_only_cypher(
    """
    MATCH path = (center)-[rel*1..1]-(related)
    WHERE center.name = $query
    UNWIND range(0, size(relationships(path)) - 1) AS idx
    WITH nodes(path)[idx] AS source_node,
         nodes(path)[idx + 1] AS target_node,
         relationships(path)[idx] AS rel
    RETURN DISTINCT
           properties(source_node) AS source,
           head(labels(source_node)) AS source_label,
           properties(target_node) AS target,
           head(labels(target_node)) AS target_label,
           type(rel) AS rel_type
    LIMIT $limit
    """
)

GRAPH_QUERY_FUZZY = ensure_read_only_cypher(
    """
    MATCH path = (center)-[rel*1..1]-(related)
    WHERE toLower(center.name) CONTAINS toLower($query)
    UNWIND range(0, size(relationships(path)) - 1) AS idx
    WITH nodes(path)[idx] AS source_node,
         nodes(path)[idx + 1] AS target_node,
         relationships(path)[idx] AS rel
    RETURN DISTINCT
           properties(source_node) AS source,
           head(labels(source_node)) AS source_label,
           properties(target_node) AS target,
           head(labels(target_node)) AS target_label,
           type(rel) AS rel_type
    LIMIT $limit
    """
)

GRAPH_QUERY_DEPTH_2_EXACT = ensure_read_only_cypher(
    """
    MATCH path = (center)-[rel*1..2]-(related)
    WHERE center.name = $query
    UNWIND range(0, size(relationships(path)) - 1) AS idx
    WITH nodes(path)[idx] AS source_node,
         nodes(path)[idx + 1] AS target_node,
         relationships(path)[idx] AS rel
    RETURN DISTINCT
           properties(source_node) AS source,
           head(labels(source_node)) AS source_label,
           properties(target_node) AS target,
           head(labels(target_node)) AS target_label,
           type(rel) AS rel_type
    LIMIT $limit
    """
)

GRAPH_QUERY_DEPTH_2_FUZZY = ensure_read_only_cypher(
    """
    MATCH path = (center)-[rel*1..2]-(related)
    WHERE toLower(center.name) CONTAINS toLower($query)
    UNWIND range(0, size(relationships(path)) - 1) AS idx
    WITH nodes(path)[idx] AS source_node,
         nodes(path)[idx + 1] AS target_node,
         relationships(path)[idx] AS rel
    RETURN DISTINCT
           properties(source_node) AS source,
           head(labels(source_node)) AS source_label,
           properties(target_node) AS target,
           head(labels(target_node)) AS target_label,
           type(rel) AS rel_type
    LIMIT $limit
    """
)


def build_knowledge_graph(neo4j_client, query, depth=1, limit=30):
    clean_query = (query or "").strip()
    clean_depth = max(1, min(int(depth or 1), 2))
    clean_limit = max(1, min(int(limit or 30), 100))
    has_exact_center = bool(
        clean_query and neo4j_client.run_cypher(EXACT_CENTER_QUERY, {"query": clean_query})
    )
    if clean_depth == 2:
        query_text = GRAPH_QUERY_DEPTH_2_EXACT if has_exact_center else GRAPH_QUERY_DEPTH_2_FUZZY
    else:
        query_text = GRAPH_QUERY_EXACT if has_exact_center else GRAPH_QUERY_FUZZY
    records = neo4j_client.run_cypher(
        query_text,
        {"query": clean_query, "depth": clean_depth, "limit": clean_limit},
    )

    nodes_by_id = {}
    edges_by_id = {}
    for record in records:
        source = node_to_public_node(record.get("source") or {}, record.get("source_label"))
        target = node_to_public_node(record.get("target") or {}, record.get("target_label"))
        nodes_by_id.setdefault(source["id"], source)
        nodes_by_id.setdefault(target["id"], target)

        edge_id = "%s-%s-%s" % (source["id"], record.get("rel_type"), target["id"])
        edges_by_id.setdefault(
            edge_id,
            {
                "id": edge_id,
                "source": source["id"],
                "target": target["id"],
                "label": record.get("rel_type") or "RELATED_TO",
            },
        )

    return {
        "nodes": list(nodes_by_id.values()),
        "edges": list(edges_by_id.values()),
    }
