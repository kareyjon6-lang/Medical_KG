import asyncio
import json
import re
from typing import List
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from __004__langgraph_more_nodes.agent_state import AgentState
from __005__fastapi.__003__msg_queue import put_think_text_to_msg, put_think_text_stream_to_msg, \
    put_think_huiche_text_to_msg
from __004__langgraph_more_nodes.nodes.runtime_config import get_thread_id
from common.config import Config
from common.llm import my_llm

conf = Config()


# 定义 Cypher 查询输出的 Pydantic 模型
class CypherQuery(BaseModel):
    query: str = Field(description="Neo4j Cypher 查询语句")


class CypherQueryList(BaseModel):
    cypher: List[CypherQuery] = Field(description="Cypher 查询语句列表")


# 初始化解析器
parser = JsonOutputParser(pydantic_object=CypherQueryList)


def extract_cypher_queries(raw_output):
    candidates = []
    parsed = None
    if isinstance(raw_output, dict):
        parsed = raw_output
    else:
        text = str(raw_output or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
        for candidate in (text, _extract_first_json_object(text)):
            if not candidate:
                continue
            try:
                parsed = parser.parse(candidate)
                break
            except Exception:
                try:
                    parsed = json.loads(candidate)
                    break
                except Exception:
                    continue

    if isinstance(parsed, dict):
        candidates = parsed.get("cypher") or parsed.get("queries") or []
    elif isinstance(parsed, list):
        candidates = parsed

    queries = []
    for item in candidates:
        query = item.get("query") if isinstance(item, dict) else item
        query = str(query or "").strip()
        if query and query not in queries:
            queries.append(query)
    return queries


def _extract_first_json_object(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start:end + 1]


def build_fallback_cypher_queries(state: AgentState):
    entity_values = []
    for key in (
        "matched_symptoms",
        "matched_diseases",
        "matched_formulas",
        "matched_herbs",
        "matched_effects",
        "matched_sources",
        "user_input_symptoms",
        "user_input_diseases",
        "user_input_formulas",
        "user_input_herbs",
        "user_input_effects",
        "user_input_sources",
    ):
        for value in state.get(key, []) or []:
            clean = str(value or "").strip().replace("\\", "\\\\").replace("'", "\\'")
            if clean and clean not in entity_values:
                entity_values.append(clean)

    if entity_values:
        names = ", ".join(f"'{value}'" for value in entity_values[:12])
        return [
            (
                "MATCH (n) "
                f"WHERE n.name IN [{names}] "
                "OPTIONAL MATCH (n)-[r]-(related) "
                "RETURN labels(n) AS entity_labels, properties(n) AS entity, "
                "type(r) AS relation, labels(related) AS related_labels, properties(related) AS related "
                "LIMIT 30"
            )
        ]

    user_input = str(state.get("input_semantic_trans") or state.get("input") or "").strip()
    if not user_input:
        return []
    query_text = user_input.replace("\\", "\\\\").replace("'", "\\'")
    return [
        (
            "MATCH (n) "
            f"WHERE n.name IS NOT NULL AND toLower(n.name) CONTAINS toLower('{query_text}') "
            "OPTIONAL MATCH (n)-[r]-(related) "
            "RETURN labels(n) AS entity_labels, properties(n) AS entity, "
            "type(r) AS relation, labels(related) AS related_labels, properties(related) AS related "
            "LIMIT 30"
        )
    ]


async def generate_neo4j_cypher_node(state: AgentState, config: RunnableConfig | None = None) -> AgentState:
    # 获取用户ID
    user_id = get_thread_id(config, state)
    print("开始生成neo4j的cypher语句")
    await put_think_text_to_msg(user_id, "开始生成Cypher查询语句")
    user_input = state["input_semantic_trans"]
    
    # 初始化或增加循环计数器
    attempts = state.get("cypher_generation_attempts", 0)
    state["cypher_generation_attempts"] = attempts + 1
    print(f"当前是第 {state['cypher_generation_attempts']} 次尝试生成 Cypher 语句")

    # 从 state 取出所有匹配到的实体
    matched_effects = state.get("matched_effects", [])
    matched_diseases = state.get("matched_diseases", [])
    matched_symptoms = state.get("matched_symptoms", [])
    matched_formulas = state.get("matched_formulas", [])
    matched_herbs = state.get("matched_herbs", [])
    matched_sources = state.get("matched_sources", [])

    meta_data = conf.TCM_METADATA  # 知识图谱元数据（节点、关系定义等）

    # 构建提示词模板
    prompt = PromptTemplate(
        template=(
            "你是一个 Neo4j Cypher 查询语句生成助手。\n"
            "请基于中医知识图谱，结合用户输入和已匹配实体，生成最合适的查询语句。\n\n"
            "用户输入：{user_input}\n\n"
            "匹配到的实体：\n"
            "- effects（功效）: {matched_effects}\n"
            "- diseases（疾病）: {matched_diseases}\n"
            "- symptoms（症状）: {matched_symptoms}\n"
            "- formulas（方剂）: {matched_formulas}\n"
            "- herbs（药材）: {matched_herbs}\n"
            "- sources（出处）: {matched_sources}\n\n"
            "知识图谱元数据（节点与关系定义）：\n"
            "{meta_data}\n\n"
            "要求：\n"
            "1. 根据用户输入语义、匹配到的实体及元数据，生成 1~N 条合适的 Cypher 查询。\n"
            "2. 禁止出现←箭头"
            "3. 输出必须符合以下格式：\n"
            "{format_instructions}"
        ),
        input_variables=["user_input", "matched_effects", "matched_diseases", "matched_symptoms", 
                         "matched_formulas", "matched_herbs", "matched_sources", "meta_data"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
        # input_variables 参数:定义提示词模板中需要从外部动态传入的变量名列表
        # partial_variables 参数: 定义提示词模板中可以预先填充或部分填充的变量
    )

    # 构建链式调用
    chain = prompt | my_llm

    # 调用链式处理
    try:
        result = ""
        for chunk in chain.stream({
            "user_input": user_input,
            "matched_effects": matched_effects,
            "matched_diseases": matched_diseases,
            "matched_symptoms": matched_symptoms,
            "matched_formulas": matched_formulas,
            "matched_herbs": matched_herbs,
            "matched_sources": matched_sources,
            "meta_data": meta_data
        }):
            result += chunk.content
            await put_think_text_stream_to_msg(user_id, chunk.content)
            print(chunk.content, end="", flush=True)
        await put_think_huiche_text_to_msg(user_id)
        cypher_queries = extract_cypher_queries(result)
        # result = chain.invoke({
        #     "user_input": user_input,
        #     "matched_effects": matched_effects,
        #     "matched_diseases": matched_diseases,
        #     "matched_symptoms": matched_symptoms,
        #     "matched_formulas": matched_formulas,
        #     "matched_herbs": matched_herbs,
        #     "matched_sources": matched_sources,
        #     "meta_data": meta_data
        # })
        
        state["cypher_query"] = cypher_queries
    except Exception as e:
        print(f"生成 Cypher 查询时出错: {str(e)}")
        state["cypher_query"] = []

    if not state.get("cypher_query"):
        fallback_queries = build_fallback_cypher_queries(state)
        if fallback_queries:
            print(f"Cypher 生成为空，使用兜底图谱证据查询: {fallback_queries}")
            state["cypher_query"] = fallback_queries

    print(f"完成生成neo4j的cypher语句{state['cypher_query']}")
    await put_think_text_to_msg(user_id, f"完成生成Cypher查询语句：{len(state['cypher_query'])}条")
    return state


if __name__ == "__main__":
    from langchain_core.runnables import RunnableConfig
    config = RunnableConfig(configurable={"thread_id": "test_user"})
    state = asyncio.run(generate_neo4j_cypher_node({"input_semantic_trans": "今天我头疼，我该吃什么药。", "matched_diseases":['头疼', '头痛']}, config))
    print(state)



