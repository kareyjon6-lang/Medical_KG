import asyncio
import json
from typing import List
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from __004__langgraph_more_nodes.agent_state import AgentState
from __005__fastapi.__003__msg_queue import put_think_text_to_msg, put_think_text_stream_to_msg, \
    put_think_huiche_text_to_msg
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


async def generate_neo4j_cypher_node(state: AgentState, config: RunnableConfig) -> AgentState:
    # 获取用户ID
    user_id = config.get("configurable", {}).get("thread_id", "")
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
        result = parser.parse(result)
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
        
        # 从解析结果中提取 cypher 查询列表
        cypher_queries = []
        if result and "cypher" in result:
            for item in result["cypher"]:
                if isinstance(item, dict) and "query" in item:
                    cypher_queries.append(item["query"])
                elif isinstance(item, str):
                    cypher_queries.append(item)
        
        state["cypher_query"] = cypher_queries
    except Exception as e:
        print(f"生成 Cypher 查询时出错: {str(e)}")
        state["cypher_query"] = []

    print(f"完成生成neo4j的cypher语句{state['cypher_query']}")
    await put_think_text_to_msg(user_id, f"完成生成Cypher查询语句：{len(state['cypher_query'])}条")
    return state


if __name__ == "__main__":
    from langchain_core.runnables import RunnableConfig
    config = RunnableConfig(configurable={"thread_id": "test_user"})
    state = asyncio.run(generate_neo4j_cypher_node({"input_semantic_trans": "今天我头疼，我该吃什么药。", "matched_diseases":['头疼', '头痛']}, config))
    print(state)
