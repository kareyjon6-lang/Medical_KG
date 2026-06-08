from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from __004__langgraph_more_nodes.agent_state import AgentState
from __005__fastapi.__003__msg_queue import put_think_text_to_msg
from common.llm import my_llm
from common.config import Config

conf = Config()


async def semantic_transcription_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    语义转写节点：
    根据历史对话内容（history_messages）和当前用户输入（input），
    生成一个更清晰、标准化的语义转写结果，用于下游意图识别或问题理解。
    """
    # 次数置为0
    # 为什么这里要置为0？因为现在初始节点是semantic_transcription_node节点，当你经过这个节点说明是重新问了一个问题，那么你里面尝试生成cypher语句次数也要置为0，
    # 不然的话问第4个问题（最多第4个，不排除一个问题不能一次成功生成）的时候会直接报“已达到最大尝试次数({attempts}次)，不再重新生成Cypher语句，直接使用大模型生成回答”，
    user_id = config.get("configurable", {}).get("thread_id", "")
    state["cypher_generation_attempts"] = 0
    # 获取用户输入和历史上下文
    print("开始生成语义转写...")
    await put_think_text_to_msg(user_id, "开始生成语义转写")
    user_input = state["input"]
    history_messages = state.get("history_messages", [])
    print(f"历史消息：{history_messages}")

    # 更新历史
    history_messages.append({"role": "user", "content": user_input})
    state["history_messages"] = history_messages
    # 只保留最近5轮
    history_messages = history_messages[-(conf.HISTORY_NUM + 1):-1]

    print("开始生成语义转写...")

    # 构建提示词
    prompt = f"""
    你是一名语言理解专家，负责将用户输入转写为清晰、简洁、语义明确的问题或意图表达。
    你需要基于以下上下文（最近5轮对话），分析用户真正想表达的意思。
    请不要编造不存在的信息，也不要直接回答问题，只需输出语义转写后的句子。
    
    【历史对话】
    {history_messages}
    
    【当前用户输入】
    {user_input}
    
    请输出：
    1. 一句自然语言，清楚表达用户当前真正的问题或意图；
    2. 不要包含解释性文字；
    3. 如果用户输入含糊不清，请基于上下文合理补全语义；
    4. 输出格式：直接输出转写结果，无需加前缀。
"""

    # 调用大模型
    response = my_llm.invoke([HumanMessage(content=prompt)])
    result = response.content.strip()

    # 保存语义转写结果
    state["input_semantic_trans"] = result
    print(f"完成生成语义转写：{result}")
    await put_think_text_to_msg(user_id, f"完成生成语义转写：{result}")
    return state
