import asyncio
from langchain_core.runnables import RunnableConfig

from __004__langgraph_more_nodes.agent_state import AgentState
from langchain_core.messages import HumanMessage

from __005__fastapi.__003__msg_queue import put_stream_text_to_msg, put_think_text_to_msg
from __004__langgraph_more_nodes.nodes.runtime_config import get_thread_id
from common.llm import llm_astream
import json


async def neo4j_answer_generate_node(state: AgentState, config: RunnableConfig | None = None) -> AgentState:
    # 获取用户ID
    user_id = get_thread_id(config, state)
    print("开始进行neo4j输入大模型的回答")
    await put_think_text_to_msg(user_id, "开始生成基于知识图谱的回答")
    user_input = state["input_semantic_trans"]
    cypher_results = state.get("cypher_results", [])

    # 把 cypher_results 转成字符串，方便喂给大模型,注意：cypher_result包括了"query": cypher_query,"result": result_list，把查询语句也放进来是为了让大模型更好理解语义
    cypher_results_str = json.dumps(cypher_results, ensure_ascii=False, indent=2)

    prompt = f"""
    你是一位严谨、安全至上的中医知识图谱问答助手。你的核心原则是：**安全第一，不误导用户自行用药**。

    用户问题：{user_input}

    【图谱查询结果（后台数据）】：
    {cypher_results_str}

    ---

    请严格遵循以下步骤生成回答，**不要跳过任何步骤**：

    **第一步：紧急情况红灯预警（最高优先级）**
    - 首先判断用户描述中是否包含“剧烈疼痛”、“刺痛拒按”、“腹部硬如木板”、“呕吐不止”、“便血/黑便”、“高烧寒战”、“女性停经后突发剧痛”等急腹症信号。
    - **如果包含**：回答必须将 **“立即前往正规医院急诊科就诊，切勿自行处理”** 放在最前面，并简要解释这些症状的危险性。
    - **如果不包含**：也必须在回答末尾附上标准就医提醒（若症状持续不缓解或加重，请及时就医）。

    **第二步：将图谱数据转化为“安全、可操作”的家庭调理方案**
    - **优先推荐无创物理疗法**：基于图谱中的“证型”或“病因”关联，优先给出热敷、穴位按摩（如足三里、中脘）、饮食禁忌（如忌生冷油腻）等零风险建议。
    - **严格限制药物/方剂的输出方式**：
      - 图谱中查询到的任何中药、方剂（如汤药、丸剂），**严禁**直接作为“推荐用药”写进回答。
      - 如果图谱确实查到了相关方剂，你只能把它们放在回答末尾的 **“附录：图谱关联药物参考（仅供医生了解，请勿自行购买服用）”** 板块中。
      - 在引用这些药物时，必须附加严重警告：“中药需辨证论治，个体差异大，必须在执业中医师指导下使用，切勿根据本条信息自行抓药。”

    **第三步：结构化输出格式（让用户一目了然）**
    请按以下Markdown结构组织回答：

    1.  **🆘 紧急情况排查**（根据第一步给出明确结论）
    2.  **🤔 自我辨证参考**（根据图谱中的证型关联，用通俗语言描述“寒痛/热痛/气滞痛/食积痛”各自的特点，帮助用户对照）
    3.  **👐 当下可行的缓解措施**（重点写热敷、按揉、食疗方<仅限生姜红糖水/山楂水等药食同源类>）
    4.  **⚠️ 就医指征**（明确什么情况下必须去医院）
    5.  **📚 图谱深度信息（仅供医生参考）**（此处再附上查询到的具体方剂/药材，并带上严厉的禁用声明）

    **第四步：数据缺失时的处理**
    - 如果图谱查询结果为空或无法匹配用户症状，请如实告知：“目前我的知识库暂未收录针对您这种情况的详细数据。” 然后结合你的通用医学常识，给出最基础的热敷、休息建议，并强调就医。

    ---

    现在，请基于以上规则，针对用户的问题“{user_input}”和背后的图谱数据，生成你的最终回答。
    """
    # print(prompt)

    model_answer = ""
    async for chunk in llm_astream([HumanMessage(content=prompt)]):
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


