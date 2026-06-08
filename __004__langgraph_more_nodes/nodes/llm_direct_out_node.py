from langchain_core.runnables import RunnableConfig
from __004__langgraph_more_nodes.agent_state import AgentState
from langchain_core.messages import HumanMessage

from __005__fastapi.__003__msg_queue import put_stream_text_to_msg, put_think_text_to_msg
from common.llm import my_llm


async def llm_direct_out_node(state: AgentState, config: RunnableConfig):
    # 获取用户ID
    user_id = config.get("configurable", {}).get("thread_id", "")
    print("开始生成直接用户回答")
    await put_think_text_to_msg(user_id, "开始生成直接回答")
    # 获取用户输入
    user_input = state["input_semantic_trans"]

    # 构建提示词（专注中医回答）
    prompt = f"""
    用户输入: {user_input}

    你是一名专业的中医知识助手，回答时请尽量基于中医理论和术语来解释。  
    要求：
    - 优先从中医角度（如症状、方剂、中药材、功效、经络、辨证论治、典籍等）进行回答。  
    - 如果问题与中医无关，就不用用中医知识回答，当成常识性问题回答。
    - 回答要准确、简洁，避免无关内容。  
    - 输出时只给出最终答案，不要解释你是如何推理的。
    """

    # 调用大模型
    model_answer = ""
    for chunk in my_llm.stream([HumanMessage(content=prompt)]):
        print(chunk.content, end="", flush=True)
        await put_stream_text_to_msg(user_id, chunk.content)
        model_answer += chunk.content

    # 存入 state
    state["direct_out"] = model_answer
    state["output"] = model_answer
    # 存入历史记录中
    state["history_messages"].append({"role": "assistant", "content": model_answer})
    print("完成生成直接用户回答")
    await put_think_text_to_msg(user_id, "完成生成直接回答")
    return state


if __name__ == "__main__":
    import asyncio
    from langchain_core.runnables import RunnableConfig


    async def main():
        config = RunnableConfig(configurable={"thread_id": "test_user"})
        # 创建一个最小的 state 用于测试
        test_state = {
            "input_semantic_trans": "火星上有外星人吗？",
            "history_messages": []
        }
        result = await llm_direct_out_node(test_state, config)
        print(result)


    asyncio.run(main())
