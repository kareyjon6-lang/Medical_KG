import asyncio

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from __004__langgraph_more_nodes.agent_state import AgentState
from __004__langgraph_more_nodes.nodes.llm_direct_out_node import llm_direct_out_node
from __004__langgraph_more_nodes.nodes.zhongyi_intent_node import zhongyi_intent_node
from __004__langgraph_more_nodes.nodes.extract_entity_from_user_input_node import extract_entity_from_user_input_node
from __004__langgraph_more_nodes.nodes.match_entity_from_neo4j_node import match_entity_from_neo4j_node
from __004__langgraph_more_nodes.nodes.generate_neo4j_cypher_node import generate_neo4j_cypher_node
from __004__langgraph_more_nodes.nodes.check_cypher_node import check_cypher_node
from __004__langgraph_more_nodes.nodes.run_cypher_node import run_cypher_node
from __004__langgraph_more_nodes.nodes.neo4j_answer_generate_node import neo4j_answer_generate_node
from __004__langgraph_more_nodes.nodes.semantic_transcription_node import semantic_transcription_node


# 这里统一编排问答图中的意图识别、实体匹配、Cypher 生成与答案生成节点。
def build_graph():
    graph_builder = StateGraph(AgentState)

    # 添加所有节点
    graph_builder.add_node(zhongyi_intent_node.__name__, zhongyi_intent_node)
    graph_builder.add_node(llm_direct_out_node.__name__, llm_direct_out_node)
    graph_builder.add_node(extract_entity_from_user_input_node.__name__, extract_entity_from_user_input_node)
    graph_builder.add_node(match_entity_from_neo4j_node.__name__, match_entity_from_neo4j_node)
    graph_builder.add_node(generate_neo4j_cypher_node.__name__, generate_neo4j_cypher_node)
    graph_builder.add_node(check_cypher_node.__name__, check_cypher_node)
    graph_builder.add_node(run_cypher_node.__name__, run_cypher_node)
    graph_builder.add_node(neo4j_answer_generate_node.__name__, neo4j_answer_generate_node)
    graph_builder.add_node(semantic_transcription_node.__name__, semantic_transcription_node)

    # 设置起始节点
    graph_builder.add_edge(START, semantic_transcription_node.__name__)
    graph_builder.add_edge(semantic_transcription_node.__name__, zhongyi_intent_node.__name__)

    # 定义中医意图识别的条件路由
    def zhongyi_intent_conditional(state: AgentState):
        if state.get("is_zhongyi_intent", False):
            return extract_entity_from_user_input_node.__name__
        else:
            return llm_direct_out_node.__name__

    # 添加条件边
    graph_builder.add_conditional_edges(zhongyi_intent_node.__name__, zhongyi_intent_conditional, path_map={
        extract_entity_from_user_input_node.__name__: extract_entity_from_user_input_node.__name__,
        llm_direct_out_node.__name__: llm_direct_out_node.__name__
    })

    # 非中医意图直接结束
    graph_builder.add_edge(llm_direct_out_node.__name__, END)

    # 中医意图的流程：实体抽取 -> 实体匹配 -> 生成Cypher -> 检查Cypher -> 运行Cypher -> 生成回答
    graph_builder.add_edge(extract_entity_from_user_input_node.__name__, match_entity_from_neo4j_node.__name__)
    graph_builder.add_edge(match_entity_from_neo4j_node.__name__, generate_neo4j_cypher_node.__name__)
    graph_builder.add_edge(generate_neo4j_cypher_node.__name__, check_cypher_node.__name__)

    # 定义Cypher检查的条件路由
    def cypher_check_conditional(state: AgentState):
        # 检查是否已达到最大尝试次数（3次）
        attempts = state.get("cypher_generation_attempts", 0)
        if attempts >= 3:
            print(f"已达到最大尝试次数({attempts}次)，不再重新生成Cypher语句，直接使用大模型生成回答")
            return neo4j_answer_generate_node.__name__

        if state.get("is_all_validate_cypher", False):
            return run_cypher_node.__name__
        else:
            # 如果Cypher语句验证失败，回退继续生成Cypher语句
            return generate_neo4j_cypher_node.__name__

    # 添加Cypher检查的条件边
    graph_builder.add_conditional_edges(check_cypher_node.__name__, cypher_check_conditional, path_map={
        run_cypher_node.__name__: run_cypher_node.__name__,
        generate_neo4j_cypher_node.__name__: generate_neo4j_cypher_node.__name__,
        neo4j_answer_generate_node.__name__: neo4j_answer_generate_node.__name__
    })

    # 运行Cypher后生成回答
    graph_builder.add_edge(run_cypher_node.__name__, neo4j_answer_generate_node.__name__)

    # 最终回答结束
    graph_builder.add_edge(neo4j_answer_generate_node.__name__, END)
    memory = InMemorySaver()
    graph = graph_builder.compile(checkpointer=memory)
    return graph


graph = build_graph()

async def zhongyi_response(input: str, user_id: str, history_messages=None):
    config = RunnableConfig(configurable={
        "thread_id": user_id
    })
    initial_state = {"input": input, "runtime_thread_id": user_id}
    if history_messages is not None:
        initial_state["history_messages"] = history_messages
    result = await graph.ainvoke(initial_state, config=config)
    return result["output"]


if __name__ == "__main__":
    result = asyncio.run(zhongyi_response("我脑袋疼，吃什么药呢？", "user_001"))
    print(result)
