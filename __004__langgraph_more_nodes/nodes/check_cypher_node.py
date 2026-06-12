from langchain_core.runnables import RunnableConfig
from __004__langgraph_more_nodes.agent_state import AgentState
from common.neo4j_manager import neo4j_client
from __005__fastapi.__003__msg_queue import put_think_text_to_msg
from __004__langgraph_more_nodes.nodes.runtime_config import get_thread_id


async def check_cypher_node(state: AgentState, config: RunnableConfig | None = None):
    # 获取用户ID
    user_id = get_thread_id(config, state)
    print("开始检查cypher语句")
    await put_think_text_to_msg(user_id, "开始验证Cypher语句语法")
    cypher_query_list = state["cypher_query"]
    state['is_all_validate_cypher'] = True
    for cypher_query in cypher_query_list:
        if not neo4j_client.validate_cypher(cypher_query):
            state['is_all_validate_cypher'] = False
    print(f"完成检查cypher语句:{state['is_all_validate_cypher']}")
    await put_think_text_to_msg(user_id, f"完成验证Cypher语句语法：{'全部通过' if state['is_all_validate_cypher'] else '存在错误'}")
    return state


if __name__ == '__main__':
    from langchain_core.runnables import RunnableConfig
    import asyncio
    config = RunnableConfig(configurable={"thread_id": "test_user"})
    print(asyncio.run(check_cypher_node({"cypher_query":["MATCH (e:Employee) RETURN e.id, e.name, e.salary, e.deptno"]}, config)))


