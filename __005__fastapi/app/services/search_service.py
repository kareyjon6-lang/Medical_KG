from __005__fastapi.app.services.cypher_guard import ensure_read_only_cypher


SEARCH_QUERY = ensure_read_only_cypher(
    """
    MATCH (n)
    WHERE n.name IS NOT NULL
      AND ($query = '' OR toLower(n.name) CONTAINS toLower($query))
      AND ($labels = '' OR any(item IN split($labels, ',') WHERE item IN labels(n) OR coalesce(n.label, '') = item))
    OPTIONAL MATCH (n)-[rel]-(related)
    WITH n,
         head(labels(n)) AS label,
         collect({
           type: type(rel),
           properties: properties(related),
           label: head(labels(related))
         }) AS related_items,
         collect(toLower(coalesce(related.name, ''))) AS related_names
    WITH n,
         label,
         related_items,
         related_names,
         toLower(coalesce(n.source, '')) AS node_source,
         toLower(coalesce(n.effect, '')) AS node_effect,
         [effect IN split($effects, '|') WHERE effect <> ''] AS effect_filters
    WHERE ($source = '' OR node_source CONTAINS toLower($source) OR any(name IN related_names WHERE name CONTAINS toLower($source)))
      AND (size(effect_filters) = 0 OR all(effect IN effect_filters WHERE node_effect CONTAINS toLower(effect) OR any(name IN related_names WHERE name CONTAINS toLower(effect))))
    RETURN properties(n) AS properties, label, related_items[0..8] AS related_items
    ORDER BY label, properties(n).name
    LIMIT $limit
    """
)


def build_search_results(neo4j_client, query, limit=10, label="", source="", effects=None):
    clean_query = (query or "").strip()
    labels = _normalize_labels(label)
    clean_labels = ",".join(labels)
    ignores_formula_filters = labels and all(item in {"Disease", "Symptom"} for item in labels)
    clean_source = "" if ignores_formula_filters else (source or "").strip()
    clean_effects = "" if ignores_formula_filters else "|".join(effect.strip() for effect in (effects or []) if effect and effect.strip())
    clean_limit = max(1, min(int(limit or 10), 3000))
    records = neo4j_client.run_cypher(
        SEARCH_QUERY,
        {
            "query": clean_query,
            "labels": clean_labels,
            "source": clean_source,
            "effects": clean_effects,
            "limit": clean_limit,
        },
    )
    return [_record_to_public_node(record) for record in records]


def _normalize_labels(label):
    if isinstance(label, (list, tuple)):
        raw_labels = label
    else:
        raw_labels = str(label or "").split(",")
    allowed = {"Formula", "Herb", "Disease", "Symptom"}
    labels = [item.strip() for item in raw_labels if item and item.strip() in allowed]
    return labels


def node_to_public_node(node, label=None):
    props = _repair_value(_node_to_dict(node))
    resolved_label = label or props.get("label") or _first_label(props) or "Entity"
    name = props.get("name") or props.get("title") or "未命名实体"
    public_props = {
        key: value
        for key, value in sorted(props.items())
        if key not in {"id", "label", "labels", "name"} and value not in (None, "")
    }
    return {
        "id": "%s:%s" % (resolved_label, name),
        "name": name,
        "label": resolved_label,
        "properties": public_props,
    }


def _record_to_public_node(record):
    if "node" in record:
        return node_to_public_node(record["node"])

    properties = dict(record.get("properties") or {})
    related_summary = _related_items_to_summary(record.get("related_items") or [])
    if related_summary:
        properties["related"] = related_summary
    if record.get("label"):
        properties["label"] = record["label"]
    return node_to_public_node(properties)


def _node_to_dict(node):
    if isinstance(node, dict):
        return dict(node)
    if hasattr(node, "items"):
        return dict(node.items())
    return dict(node or {})


def _repair_value(value):
    if isinstance(value, str):
        return _repair_mojibake(value)
    if isinstance(value, dict):
        return {key: _repair_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_repair_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_repair_value(item) for item in value)
    return value


def _repair_mojibake(value):
    if not _looks_like_mojibake(value):
        return value
    try:
        repaired = value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value
    return repaired if _looks_more_readable(repaired, value) else value


def _looks_like_mojibake(value):
    markers = ("Ã", "Â", "ä", "å", "æ", "ç", "è", "é", "ï", "ð")
    return any(marker in value for marker in markers)


def _looks_more_readable(candidate, original):
    cjk_count = sum("\u4e00" <= char <= "\u9fff" for char in candidate)
    mojibake_count = sum(char in "ÃÂäåæçèéïð" for char in candidate)
    original_mojibake_count = sum(char in "ÃÂäåæçèéïð" for char in original)
    return cjk_count > 0 and mojibake_count < original_mojibake_count


def _first_label(props):
    labels = props.get("labels")
    if isinstance(labels, (list, tuple)) and labels:
        return labels[0]
    return None


def _related_items_to_summary(items):
    pieces = []
    for item in items:
        if not item or not item.get("type"):
            continue
        related_props = _repair_value(item.get("properties") or {})
        name = related_props.get("name") or related_props.get("title")
        if not name:
            continue
        relation = _relation_label(item.get("type"))
        label = _entity_label(item.get("label"))
        pieces.append(f"{relation}：{name}（{label}）")
    return "；".join(dict.fromkeys(pieces))


def _relation_label(label):
    return {
        "HAS_INGREDIENT": "组成",
        "ALLEVIATES_SYMPTOM": "缓解症状",
        "TREATS_DISEASE": "治疗疾病",
        "HAS_EFFECT": "具有功效",
        "BELONGS_TO_CATEGORY": "属于分类",
        "FROM_SOURCE": "出自",
        "HAS_NATURE": "药性",
        "HAS_FLAVOR": "药味",
        "ENTERS_MERIDIAN": "归经",
        "RELATED_TO": "相关",
    }.get(label, str(label or "").replace("_", ""))


def _entity_label(label):
    return {
        "Formula": "方剂",
        "Herb": "药材",
        "Symptom": "症状",
        "Disease": "疾病",
        "Effect": "功效",
        "Source": "出处",
        "FormulaCategory": "方剂分类",
        "HerbNature": "药性",
        "HerbFlavor": "药味",
        "Meridian": "归经",
    }.get(label, label or "实体")
