from __005__fastapi.app.services.cypher_guard import ensure_read_only_cypher
from __005__fastapi.app.services.search_service import node_to_public_node


GRAPH_QUERY = ensure_read_only_cypher(
    """
    MATCH (center)-[rel]-(related)
    WHERE center.name = $query OR toLower(center.name) CONTAINS toLower($query)
    RETURN properties(center) AS center,
           head(labels(center)) AS center_label,
           properties(related) AS related,
           head(labels(related)) AS related_label,
           type(rel) AS rel_type
    LIMIT $limit
    """
)

GRAPH_QUERY_DEPTH_2 = ensure_read_only_cypher(
    """
    MATCH path = (center)-[rel*1..2]-(related)
    WHERE center.name = $query OR toLower(center.name) CONTAINS toLower($query)
    WITH center, related, relationships(path)[-1] AS last_rel
    RETURN properties(center) AS center,
           head(labels(center)) AS center_label,
           properties(related) AS related,
           head(labels(related)) AS related_label,
           type(last_rel) AS rel_type
    LIMIT $limit
    """
)


def build_knowledge_graph(neo4j_client, query, depth=1, limit=30):
    clean_query = (query or "").strip()
    clean_depth = max(1, min(int(depth or 1), 2))
    clean_limit = max(1, min(int(limit or 30), 100))
    query_text = GRAPH_QUERY_DEPTH_2 if clean_depth == 2 else GRAPH_QUERY
    records = neo4j_client.run_cypher(
        query_text,
        {"query": clean_query, "depth": clean_depth, "limit": clean_limit},
    )

    nodes_by_id = {}
    edges_by_id = {}
    for record in records:
        center = node_to_public_node(record.get("center") or {}, record.get("center_label"))
        related = node_to_public_node(record.get("related") or {}, record.get("related_label"))
        nodes_by_id.setdefault(center["id"], center)
        nodes_by_id.setdefault(related["id"], related)

        edge_id = "%s-%s-%s" % (center["id"], record.get("rel_type"), related["id"])
        edges_by_id.setdefault(
            edge_id,
            {
                "id": edge_id,
                "source": center["id"],
                "target": related["id"],
                "label": record.get("rel_type") or "RELATED_TO",
            },
        )

    return {
        "nodes": list(nodes_by_id.values()),
        "edges": list(edges_by_id.values()),
    }
