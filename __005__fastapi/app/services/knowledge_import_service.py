import json
import pickle
import re
import threading
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any, Dict, Iterable, List

from langchain_core.messages import HumanMessage

from common.config import Config
from common.llm import my_llm
from common.path_utils import get_file_path


MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".txt", ".txtx", ".md", ".pdf", ".docx"}
RELATION_TYPES = {"HAS_INGREDIENT", "HAS_EFFECT", "TREATS_DISEASE", "ALLEVIATES_SYMPTOM", "FROM_SOURCE"}
LABEL_TYPES = {"Formula", "Herb", "Effect", "Disease", "Symptom", "Source", "Entity"}
HERB_FIELDS = (
    "name",
    "label",
    "source",
    "origin",
    "ingredients",
    "property_flavor",
    "effect",
    "indication",
    "meridian",
    "dosage",
    "usage",
    "taboo",
    "note",
)
FORMULA_ENTITY_LABELS = ("Formula", "Herb")
_runtime_refresh_lock = threading.Lock()
_runtime_refresh_running = False
_runtime_refresh_requested = False


class FormulaNotFoundError(ValueError):
    def __init__(self, name: str, suggestions: List[str] | None = None):
        self.name = name
        self.suggestions = suggestions or []
        message = f"未在知识图谱中找到方药：{name}"
        if self.suggestions:
            message += "。可参考相似名称：" + "、".join(self.suggestions)
        super().__init__(message)


def parse_document_text(filename: str, content: bytes) -> str:
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("文件超过 20MB，请拆分后上传。")
    extension = _extension(filename)
    if extension == ".doc":
        raise ValueError("暂不支持传统 .doc 文件，请转换为 .docx 后上传。")
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("仅支持 txt、txtx、md、pdf、docx 文件。")
    if extension in {".txt", ".txtx", ".md"}:
        text = _decode_text(content)
    elif extension == ".pdf":
        text = _read_pdf(content)
    else:
        text = _read_docx(content)
    text = _normalize_document_text(text)
    if len(_normalize_text(text)) < 10:
        raise ValueError("文档内容过短，无法抽取药材知识。")
    return text


def extract_herb_knowledge(text: str, llm=None) -> Dict[str, Any]:
    document_text = _normalize_document_text(text)
    clean_text = _normalize_text(document_text)
    if len(clean_text) < 10:
        raise ValueError("请输入更完整的药材资料。")
    structured_payload = _extract_structured_herb_document(document_text)
    if structured_payload:
        return normalize_knowledge_payload(structured_payload)
    model = llm or my_llm
    prompt = _build_extraction_prompt(document_text[:12000])
    response = model.invoke([HumanMessage(content=prompt)])
    raw_content = getattr(response, "content", response)
    payload = _parse_json_object(str(raw_content or ""))
    return normalize_knowledge_payload(payload)


def normalize_knowledge_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    herb = payload.get("herb") if isinstance(payload, dict) else {}
    if not isinstance(herb, dict):
        herb = {}
    normalized_herb = {field: _clean_text(herb.get(field, "")) for field in HERB_FIELDS}
    normalized_herb["label"] = _clean_label(normalized_herb.get("label") or "Herb")
    if not normalized_herb["name"]:
        raise ValueError("AI 抽取结果缺少药材名称，请补充后再入库。")

    relations = []
    for relation in payload.get("relations", []) if isinstance(payload, dict) else []:
        if not isinstance(relation, dict):
            continue
        clean_relation = {
            "subject": _clean_text(relation.get("subject") or normalized_herb["name"]),
            "subject_type": _clean_label(relation.get("subject_type") or normalized_herb["label"]),
            "relation": _clean_relation(relation.get("relation")),
            "object": _clean_text(relation.get("object")),
            "object_type": _clean_label(relation.get("object_type") or "Entity"),
        }
        if clean_relation["subject"] and clean_relation["object"] and clean_relation["relation"]:
            relations.append(clean_relation)

    return {"herb": normalized_herb, "relations": _dedupe_relations(relations)}


def import_knowledge_to_neo4j(neo4j_client, payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_knowledge_payload(payload)
    herb = normalized["herb"]
    relations = normalized["relations"]
    subject_label = _clean_label(herb.get("label") or "Herb")
    queries = [
        (
            f"""
            MERGE (n:{subject_label} {{name: $name}})
            SET n += $props
            """,
            {"name": herb["name"], "props": _herb_props(herb)},
        )
    ]
    entity_names = {herb["name"]}
    for relation in relations:
        queries.append(_create_related_entity_query(relation))
        queries.append(_create_relation_query(relation))
        entity_names.add(relation["object"])
    neo4j_client.run_multiple_cypher(queries)
    refresh_graph_metadata(neo4j_client)
    appended = append_entities_to_runtime_index(entity_names)
    return {
        "entities": len(entity_names),
        "relations": len(relations),
        "index_refresh": "incremental",
        "index_added": appended,
    }


def build_preview_graph(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    normalized = normalize_knowledge_payload(payload)
    herb = normalized["herb"]
    subject_label = _clean_label(herb.get("label") or "Herb")
    center_id = f"{subject_label}:{herb['name']}"
    nodes_by_id: Dict[str, Dict[str, Any]] = {
        center_id: {
            "id": center_id,
            "name": herb["name"],
            "label": subject_label,
            "properties": _herb_props(herb),
        }
    }
    edges_by_id: Dict[str, Dict[str, Any]] = {}
    for relation in normalized["relations"]:
        subject_name = _clean_text(relation.get("subject") or herb["name"])
        subject_type = _clean_label(relation.get("subject_type") or subject_label)
        subject_id = f"{subject_type}:{subject_name}"
        nodes_by_id.setdefault(
            subject_id,
            {
                "id": subject_id,
                "name": subject_name,
                "label": subject_type,
                "properties": _herb_props(herb) if subject_id == center_id else {},
            },
        )
        object_label = _clean_label(relation.get("object_type") or "Entity")
        object_id = f"{object_label}:{relation['object']}"
        nodes_by_id.setdefault(
            object_id,
            {"id": object_id, "name": relation["object"], "label": object_label, "properties": {}},
        )
        edge_id = f"{subject_id}-{relation['relation']}-{object_id}"
        edges_by_id.setdefault(
            edge_id,
            {"id": edge_id, "source": subject_id, "target": object_id, "label": relation["relation"]},
        )
    return {"nodes": list(nodes_by_id.values()), "edges": list(edges_by_id.values())}


def delete_formula_from_neo4j(neo4j_client, name: str) -> Dict[str, Any]:
    clean_name = _normalize_text(name)
    if not clean_name:
        raise ValueError("请输入要删除的方药名称。")

    existing = find_formula_entity(neo4j_client, clean_name)
    if not existing:
        raise FormulaNotFoundError(clean_name, suggest_similar_formula_names(neo4j_client, clean_name))

    records = neo4j_client.run_cypher(
        """
        MATCH (n)
        WHERE n.name = $name AND any(label IN labels(n) WHERE label IN $labels)
        WITH collect(n) AS nodes, count(n) AS deleted
        UNWIND nodes AS node
        DETACH DELETE node
        RETURN deleted
        """,
        {"name": clean_name, "labels": list(FORMULA_ENTITY_LABELS)},
    )
    deleted = int((records[0] if records else {}).get("deleted") or 0)
    if deleted <= 0:
        raise FormulaNotFoundError(clean_name, suggest_similar_formula_names(neo4j_client, clean_name))

    refresh_graph_metadata(neo4j_client)
    removed = remove_entities_from_runtime_index([clean_name])
    return {
        "deleted": deleted,
        "name": clean_name,
        "labels": existing.get("labels", []),
        "index_refresh": "masked",
        "index_removed": removed,
    }


def find_formula_entity(neo4j_client, name: str) -> Dict[str, Any] | None:
    clean_name = _normalize_text(name)
    if not clean_name:
        return None
    records = neo4j_client.run_cypher(
        """
        MATCH (n)
        WHERE n.name = $name AND any(label IN labels(n) WHERE label IN $labels)
        RETURN n.name AS name, labels(n) AS labels
        LIMIT 1
        """,
        {"name": clean_name, "labels": list(FORMULA_ENTITY_LABELS)},
    )
    return records[0] if records else None


def suggest_similar_formula_names(neo4j_client, name: str, limit: int = 5) -> List[str]:
    clean_name = _normalize_text(name)
    if not clean_name:
        return []
    candidates: List[str] = []
    for label in FORMULA_ENTITY_LABELS:
        try:
            candidates.extend(neo4j_client.get_all_node_names(label))
        except Exception:
            continue
    unique_candidates = sorted({candidate for candidate in candidates if candidate})
    scored = []
    for candidate in unique_candidates:
        if candidate == clean_name:
            continue
        ratio = SequenceMatcher(None, clean_name, candidate).ratio()
        if clean_name in candidate or candidate in clean_name:
            ratio += 0.35
        if ratio >= 0.35:
            scored.append((ratio, candidate))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [candidate for _score, candidate in scored[:limit]]


def refresh_graph_metadata(neo4j_client) -> None:
    try:
        neo4j_client.export_tcm_metadata_to_json(get_file_path("__003__create_neo4j_database/tcm_metadata.json"))
    except Exception as exc:
        print(f"刷新图谱元数据失败: {exc}")
    try:
        Config().TCM_METADATA
    except Exception:
        pass


def append_entities_to_runtime_index(entity_names: Iterable[str]) -> int:
    clean_names = sorted({_normalize_text(name) for name in entity_names if _normalize_text(name)})
    if not clean_names:
        return 0

    try:
        import faiss

        from __003__create_neo4j_database.__003__faiss_embedding import text_to_embeddings
        from __004__langgraph_more_nodes.nodes import match_entity_from_neo4j_node as match_node

        index = match_node.zhongyi_index or match_node.load_index()
        id2text = dict(match_node.zhongyi_id2text or match_node.load_id2text())
        existing = {text for text in id2text.values() if text}
        pending = [name for name in clean_names if name not in existing]
        if not pending:
            return 0

        print(f"增量刷新 FAISS 实体索引：新增 {len(pending)} 个实体。")
        vectors = text_to_embeddings(pending)
        faiss.normalize_L2(vectors)
        start_id = int(index.ntotal)
        index.add(vectors)
        for offset, text in enumerate(pending):
            id2text[start_id + offset] = text

        faiss.write_index(index, match_node.INDEX_PATH)
        with open(match_node.ID2TEXT_PATH, "wb") as file:
            pickle.dump(id2text, file)
        match_node.zhongyi_index = index
        match_node.zhongyi_id2text = id2text
        return len(pending)
    except Exception as exc:
        print(f"增量刷新 FAISS 实体索引失败: {exc}")
        return 0


def remove_entities_from_runtime_index(entity_names: Iterable[str]) -> int:
    clean_names = {_normalize_text(name) for name in entity_names if _normalize_text(name)}
    if not clean_names:
        return 0

    try:
        from __004__langgraph_more_nodes.nodes import match_entity_from_neo4j_node as match_node

        id2text = dict(match_node.zhongyi_id2text or match_node.load_id2text())
        removed_ids = [idx for idx, text in id2text.items() if text in clean_names]
        for idx in removed_ids:
            id2text.pop(idx, None)
        if not removed_ids:
            return 0

        with open(match_node.ID2TEXT_PATH, "wb") as file:
            pickle.dump(id2text, file)
        match_node.zhongyi_id2text = id2text
        print(f"已从 FAISS 文本映射中屏蔽 {len(removed_ids)} 个已删除实体。")
        return len(removed_ids)
    except Exception as exc:
        print(f"屏蔽已删除实体的 FAISS 文本映射失败: {exc}")
        return 0


def refresh_graph_runtime_artifacts(neo4j_client) -> None:
    refresh_graph_metadata(neo4j_client)
    try:
        from __003__create_neo4j_database.__003__faiss_embedding import store_texts

        names = neo4j_client.get_all_node_names()
        if names:
            store_texts(names)
            try:
                from __004__langgraph_more_nodes.nodes import match_entity_from_neo4j_node as match_node

                match_node.zhongyi_index = match_node.load_index()
                match_node.zhongyi_id2text = match_node.load_id2text()
            except Exception as exc:
                print(f"重载运行时 FAISS 实体索引失败: {exc}")
    except Exception as exc:
        print(f"刷新 FAISS 实体索引失败: {exc}")
    try:
        Config().TCM_METADATA
    except Exception:
        pass


def schedule_graph_runtime_refresh(neo4j_client) -> None:
    """Queue one background metadata/FAISS rebuild and merge repeated requests."""
    global _runtime_refresh_running, _runtime_refresh_requested
    with _runtime_refresh_lock:
        if _runtime_refresh_running:
            _runtime_refresh_requested = True
            return
        _runtime_refresh_running = True
        _runtime_refresh_requested = False

    def worker() -> None:
        global _runtime_refresh_running, _runtime_refresh_requested
        while True:
            try:
                refresh_graph_runtime_artifacts(neo4j_client)
            finally:
                with _runtime_refresh_lock:
                    if _runtime_refresh_requested:
                        _runtime_refresh_requested = False
                        continue
                    _runtime_refresh_running = False
                    return

    threading.Thread(target=worker, name="tcm-graph-runtime-refresh", daemon=True).start()


def summarize_source_text(text: str, limit: int = 500) -> str:
    clean = _normalize_text(text)
    return clean[:limit] + ("..." if len(clean) > limit else "")


def _extract_structured_herb_document(text: str) -> Dict[str, Any]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return {}
    joined = "\n".join(lines)
    if not any(marker in joined for marker in ("【中药名称】", "【方剂名称】", "功效", "功用", "主治", "性味", "用法用量", "组成")):
        return {}

    formula_name = _match_first(r"【方剂名称】\s*([^\n]+)", joined)
    name = formula_name or _match_first(r"【中药名称】\s*([^\n]+)", joined)
    if not name:
        for index, line in enumerate(lines):
            if line in {"名称", "中药名称", "方剂名称"} and index + 1 < len(lines):
                name = lines[index + 1]
                break
    if not name:
        return {}

    is_formula = bool(formula_name) or any(heading in joined for heading in ("组成", "方歌", "功用"))
    ingredients = _section_text(lines, "组成", _STRUCTURED_SECTION_HEADINGS)
    source = _section_text(lines, "出处", _STRUCTURED_SECTION_HEADINGS)
    effect = _section_text(lines, "功用", _STRUCTURED_SECTION_HEADINGS) or _section_text(lines, "功效", _STRUCTURED_SECTION_HEADINGS)
    indication = _section_text(lines, "主治", _STRUCTURED_SECTION_HEADINGS)
    herb = {
        "name": _clean_heading_value(name),
        "label": "Formula" if is_formula else "Herb",
        "source": source,
        "ingredients": ingredients,
        "origin": _section_text(lines, "来源", _STRUCTURED_SECTION_HEADINGS),
        "property_flavor": _section_text(lines, "性味", _STRUCTURED_SECTION_HEADINGS),
        "effect": effect,
        "indication": indication,
        "meridian": _section_text(lines, "经脉", _STRUCTURED_SECTION_HEADINGS) or _section_text(lines, "归经", _STRUCTURED_SECTION_HEADINGS),
        "dosage": _section_text(lines, "用法用量", _STRUCTURED_SECTION_HEADINGS),
        "usage": _section_text(lines, "用法", _STRUCTURED_SECTION_HEADINGS),
        "taboo": _section_text(lines, "注意禁忌", _STRUCTURED_SECTION_HEADINGS) or _section_text(lines, "禁忌", _STRUCTURED_SECTION_HEADINGS),
        "note": _section_text(lines, "解释", _STRUCTURED_SECTION_HEADINGS) or _section_text(lines, "炮制", _STRUCTURED_SECTION_HEADINGS),
    }

    if not any(herb[field] for field in HERB_FIELDS if field != "name"):
        return {}

    relations = []
    subject_type = herb["label"]
    for ingredient in _split_ingredients(herb["ingredients"]):
        relations.append({"subject": herb["name"], "subject_type": subject_type, "relation": "HAS_INGREDIENT", "object": ingredient, "object_type": "Herb"})
    for effect_name in _split_terms(herb["effect"], mode="effect"):
        relations.append({"subject": herb["name"], "subject_type": subject_type, "relation": "HAS_EFFECT", "object": effect_name, "object_type": "Effect"})
    for symptom in _split_terms(herb["indication"], mode="symptom"):
        relation_type = "TREATS_DISEASE" if _looks_like_disease(symptom) else "ALLEVIATES_SYMPTOM"
        object_type = "Disease" if relation_type == "TREATS_DISEASE" else "Symptom"
        relations.append({"subject": herb["name"], "subject_type": subject_type, "relation": relation_type, "object": symptom, "object_type": object_type})
    source_names = {
        normalized_source
        for raw_source in re.findall(r"《([^》]{1,24})》", joined) + ([source] if source else [])
        if (normalized_source := _normalize_source_name(raw_source))
    }
    for source_name in sorted(source_names):
        relations.append({"subject": herb["name"], "subject_type": subject_type, "relation": "FROM_SOURCE", "object": source_name, "object_type": "Source"})

    return {"herb": herb, "relations": relations}


_STRUCTURED_SECTION_HEADINGS = {
    "名称",
    "来源",
    "出处",
    "组成",
    "性味",
    "炮制",
    "性状",
    "功效",
    "功用",
    "主治",
    "解释",
    "经脉",
    "归经",
    "用法用量",
    "用法",
    "注意禁忌",
    "禁忌",
    "方歌",
}


def _section_text(lines: List[str], heading: str, headings: set) -> str:
    start = -1
    for index, line in enumerate(lines):
        if line == heading or line.startswith(f"{heading} "):
            start = index
            break
    if start == -1:
        pattern = re.compile(rf"^{re.escape(heading)}(.+)$")
        for line in lines:
            match = pattern.match(line)
            if match:
                return _clean_heading_value(match.group(1))
        return ""

    chunks: List[str] = []
    for line in lines[start + 1 :]:
        clean_line = line.strip()
        if clean_line in headings or clean_line.startswith("【"):
            break
        if clean_line.endswith("的效果") or clean_line.endswith("的药方"):
            break
        chunks.append(clean_line)
    return _clean_heading_value(" ".join(chunks))


def _split_terms(text: str, mode: str = "term") -> List[str]:
    clean = _normalize_text(text)
    clean = re.sub(r"(?:用于|主治|治疗|治)\s*", "", clean)
    clean = re.sub(r"[；;。]", "，", clean)
    terms = []
    for part in re.split(r"[，、,]", clean):
        term = _clean_heading_value(part)
        term = re.sub(r"^(或|及|并|兼|见|诸|各|等|证见)", "", term).strip()
        term = re.sub(r"(等证|等症|等)$", "", term).strip()
        if not term or len(term) > 30:
            continue
        if mode == "effect" and any(word in term for word in ("本方", "用于", "适用于")):
            continue
        if term.startswith(("治", "为")) and len(term) > 8:
            term = re.sub(r"^[治为]\s*", "", term).strip()
        if term:
            terms.append(term)
    return list(dict.fromkeys(terms))[:24]


def _looks_like_disease(text: str) -> bool:
    return bool(re.search(r"(病|证|伤寒|温病|痹证|痢疾|疟疾)$", text or ""))


def _split_inline_ingredient_text(text: str) -> str:
    clean = _normalize_text(text)
    clean = re.sub(r"(?:上药|右|以上).*$", "", clean)
    return clean


def _split_ingredients(text: str) -> List[str]:
    clean = _split_inline_ingredient_text(text)
    clean = re.sub(r"（[^）]*）|\([^)]*\)", "", clean)
    clean = re.sub(r"\d+(?:\.\d+)?\s*(?:克|枚|钱|两|g|G|毫升|ml|ML|片|粒|个|分)", "，", clean)
    clean = re.sub(r"[。；;、，]", "，", clean)
    clean = re.sub(r"\s+", "，", clean)
    ingredients = []
    for part in clean.split("，"):
        item = _clean_heading_value(part)
        item = re.sub(r"^(各|共|同|先|后|另|即)", "", item).strip()
        item = re.sub(r"^(生|炙|炒|制|煅|酒|醋|盐|蜜)", lambda match: match.group(1), item)
        item = re.sub(r"(作为.*|用于.*|适宜.*)$", "", item).strip()
        if item and 1 < len(item) <= 12:
            ingredients.append(item)
    return list(dict.fromkeys(ingredients))[:24]


def _clean_heading_value(value: str) -> str:
    clean = re.sub(r"^[-#\d\.\s]+", "", str(value or "").strip())
    return _normalize_text(clean)


def _normalize_source_name(value: str) -> str:
    return _clean_heading_value(value).strip("《》")


def _match_first(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _build_extraction_prompt(text: str) -> str:
    return (
        "你是中医知识图谱入库助手。请从资料中识别一个中医方剂或药材条目，并输出严格 JSON。\n"
        "不要输出 Markdown，不要输出解释。\n\n"
        "JSON 格式如下：\n"
        "{\n"
        '  "herb": {\n'
        '    "name": "方剂或药材名称",\n'
        '    "label": "Formula 或 Herb",\n'
        '    "source": "出处",\n'
        '    "ingredients": "组成",\n'
        '    "origin": "来源或基原",\n'
        '    "property_flavor": "性味",\n'
        '    "effect": "功效",\n'
        '    "indication": "主治",\n'
        '    "meridian": "归经",\n'
        '    "dosage": "用量用法",\n'
        '    "usage": "用法",\n'
        '    "taboo": "禁忌",\n'
        '    "note": "备注"\n'
        "  },\n"
        '  "relations": [\n'
        '    {"subject": "方剂或药材名称", "subject_type": "Formula", "relation": "HAS_INGREDIENT", "object": "组成药材", "object_type": "Herb"}\n'
        "  ]\n"
        "}\n\n"
        "关系类型只能使用 HAS_INGREDIENT、HAS_EFFECT、TREATS_DISEASE、ALLEVIATES_SYMPTOM、FROM_SOURCE。\n"
        "节点类型只能使用 Formula、Herb、Effect、Disease、Symptom、Source。\n"
        "无法确定的字段输出空字符串，不能编造不存在的信息。\n\n"
        f"资料：\n{text}"
    )


def _read_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("后端缺少 pypdf 依赖，无法解析 PDF。") from exc
    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(content: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise ValueError("后端缺少 python-docx 依赖，无法解析 DOCX。") from exc
    document = Document(BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _parse_json_object(text: str) -> Dict[str, Any]:
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    candidates = [clean]
    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end > start:
        candidates.append(clean[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    raise ValueError("AI 抽取结果不是合法 JSON，请重新抽取。")


def _create_related_entity_query(relation: Dict[str, str]):
    label = relation["object_type"]
    return (
        f"""
        MERGE (n:{label} {{name: $name}})
        """,
        {"name": relation["object"]},
    )


def _create_relation_query(relation: Dict[str, str]):
    subject_type = relation["subject_type"]
    object_type = relation["object_type"]
    relation_type = relation["relation"]
    return (
        f"""
        MATCH (a:{subject_type} {{name: $subject}})
        MATCH (b:{object_type} {{name: $object}})
        MERGE (a)-[r:{relation_type}]->(b)
        """,
        {"subject": relation["subject"], "object": relation["object"]},
    )


def _herb_props(herb: Dict[str, str]) -> Dict[str, str]:
    return {key: value for key, value in herb.items() if value}


def _dedupe_relations(relations: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    unique = []
    for relation in relations:
        key = (
            relation["subject"],
            relation["subject_type"],
            relation["relation"],
            relation["object"],
            relation["object_type"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(relation)
    return unique


def _clean_label(value: Any) -> str:
    label = re.sub(r"[^A-Za-z]", "", str(value or "Entity"))
    return label if label in LABEL_TYPES else "Entity"


def _clean_relation(value: Any) -> str:
    relation = re.sub(r"[^A-Z_]", "", str(value or ""))
    return relation if relation in RELATION_TYPES else ""


def _clean_text(value: Any) -> str:
    return _normalize_text(str(value or ""))


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\u3000", " ")).strip()


def _normalize_document_text(text: str) -> str:
    lines = []
    for line in str(text or "").replace("\u3000", " ").splitlines():
        clean_line = re.sub(r"[ \t]+", " ", line).strip()
        if clean_line:
            lines.append(clean_line)
    return "\n".join(lines)


def _extension(filename: str) -> str:
    name = str(filename or "").strip().lower()
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1]
