import asyncio
from langchain_core.runnables import RunnableConfig

from __004__langgraph_more_nodes.agent_state import AgentState
from langchain_core.messages import HumanMessage

from __005__fastapi.__003__msg_queue import put_stream_text_to_msg, put_think_text_to_msg
from common.llm import my_llm
import json


async def neo4j_answer_generate_node(state: AgentState, config: RunnableConfig) -> AgentState:
    # 获取用户ID
    user_id = config.get("configurable", {}).get("thread_id", "")
    print("开始进行neo4j输入大模型的回答")
    await put_think_text_to_msg(user_id, "开始生成基于知识图谱的回答")
    user_input = state["input_semantic_trans"]
    cypher_results = state.get("cypher_results", [])

    # 把 cypher_results 转成字符串，方便喂给大模型,注意：cypher_result包括了"query": cypher_query,"result": result_list，把查询语句也放进来是为了让大模型更好理解语义
    cypher_results_str = json.dumps(cypher_results, ensure_ascii=False, indent=2)

    prompt = f"""
    你是一个中医知识图谱问答助手。
    用户提出了问题：{user_input}

    我已经在 Neo4j 图数据库中执行了查询，查询结果如下：
    {cypher_results_str}

    请你根据这些查询结果，用简洁、清晰、自然的中文回答用户的问题。
    如果查询结果无法回答用户的问题，请如实告知用户没有找到相关答案。
    """
    # print(prompt)

    model_answer = ""
    for chunk in my_llm.stream([HumanMessage(content=prompt)]):
        print(chunk.content, end="", flush=True)
        await put_stream_text_to_msg(user_id, chunk.content)
        model_answer += chunk.content


    # 保存结果
    state["neo4j_answer"] = model_answer
    state["output"] = model_answer
    # 存入历史消息中
    state["history_messages"].append({"role": "assistant", "content": model_answer})
    print("完成进行neo4j输入大模型的回答")
    await put_think_text_to_msg(user_id, "完成生成基于知识图谱的回答")

    return state