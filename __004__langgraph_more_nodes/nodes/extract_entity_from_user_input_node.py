import json
from langchain_core.runnables import RunnableConfig
from __004__langgraph_more_nodes.agent_state import AgentState
from langchain_core.messages import HumanMessage

from __005__fastapi.__003__msg_queue import put_think_text_to_msg
from common.llm import my_llm


async def extract_entity_from_user_input_node(state: AgentState, config: RunnableConfig) -> AgentState:
    # 获取用户ID
    user_id = config.get("configurable", {}).get("thread_id", "")
    print("开始从用户输入中抽取实体")
    await put_think_text_to_msg(user_id, "开始从用户输入中抽取中医实体")
    user_input = state["input_semantic_trans"]

    # 构建提示词
    prompt = f"""
    你是一个中医知识图谱的实体抽取助手。
    请从以下用户输入中抽取六类实体：
    1. Symptom（症状），如咳嗽、腹痛等
    2. Disease（疾病），如感冒、肺炎、肾虚等
    3. Formula（方剂），如四君子汤、桂枝汤等
    4. Herb（药材），如人参、黄芪、丁香等
    5. Effect（功效），如补气、活血、祛湿、止痛等
    6. Source（出处），如《本草纲目》《伤寒论》等

    要求：
    - 只输出严格的 JSON 格式
    - JSON 格式如下：
    {{
        "symptoms": ["..."],
        "diseases": ["..."],
        "formulas": ["..."],
        "herbs": ["..."],
        "effects": ["..."],
        "sources": ["..."]
    }}
    - 如果某类实体不存在，请返回空列表 []

    用户输入：{user_input}
    """

    # 调用大模型
    response = my_llm.invoke([HumanMessage(content=prompt)])
    raw_output = response.content.strip()

    try:
        entities = json.loads(raw_output)
    except json.JSONDecodeError:
        # 如果大模型没严格遵守 JSON 格式，兜底
        entities = {
            "symptoms": [],
            "diseases": [],
            "formulas": [],
            "herbs": [],
            "effects": [],
            "sources": []
        }

    # 存入 state
    state["user_input_symptoms"] = entities.get("symptoms", [])
    state["user_input_diseases"] = entities.get("diseases", [])
    state["user_input_formulas"] = entities.get("formulas", [])
    state["user_input_herbs"] = entities.get("herbs", [])
    state["user_input_effects"] = entities.get("effects", [])
    state["user_input_sources"] = entities.get("sources", [])

    print("完成从用户输入中抽取实体")
    await put_think_text_to_msg(user_id, "完成从用户输入中抽取中医实体")
    return state


if __name__ == '__main__':
    from langchain_core.runnables import RunnableConfig
    import asyncio


    async def main():
        config = RunnableConfig(configurable={"thread_id": "test_user"})
        test_state = {
            "input_semantic_trans": "我有点脑袋疼",
            "history_messages": []
        }
        result = await extract_entity_from_user_input_node(test_state, config)
        print(result)


    asyncio.run(main())
