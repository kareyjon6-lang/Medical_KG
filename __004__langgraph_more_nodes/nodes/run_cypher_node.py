from langchain_core.runnables import RunnableConfig
from __004__langgraph_more_nodes.agent_state import AgentState
from common.neo4j_manager import neo4j_client
from __005__fastapi.__003__msg_queue import put_think_text_to_msg


async def run_cypher_node(state: AgentState, config: RunnableConfig):
    # 获取用户ID
    user_id = config.get("configurable", {}).get("thread_id", "")
    print("开始运行大模型cypher语句")
    await put_think_text_to_msg(user_id, "开始执行Cypher查询语句")
    cypher_query_list = state.get("cypher_query", [])
    query_results = []

    for cypher_query in cypher_query_list:
        result_list = neo4j_client.run_cypher(cypher_query)
        query_results.append({
            "query": cypher_query,
            "result": result_list
        })

    # 存入 state
    state["cypher_results"] = query_results
    print("完成运行大模型cypher语句")
    await put_think_text_to_msg(user_id, f"完成执行Cypher查询语句，共{len(query_results)}条结果")
    return state