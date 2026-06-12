from langchain_core.runnables import RunnableConfig

from __004__langgraph_more_nodes.agent_state import AgentState
from __005__fastapi.__003__msg_queue import put_think_text_to_msg
from common.tcm_entity_extractor import entities_to_state_fields, extract_tcm_entities
from __004__langgraph_more_nodes.nodes.runtime_config import get_thread_id


async def extract_entity_from_user_input_node(state: AgentState, config: RunnableConfig | None = None) -> AgentState:
    user_id = get_thread_id(config, state)
    user_input = state.get("input_semantic_trans") or state.get("input") or ""

    print("开始从用户输入中抽取中医实体")
    await put_think_text_to_msg(user_id, "开始从用户输入中抽取中医实体")

    entities = extract_tcm_entities(user_input)
    state.update(entities_to_state_fields(entities))

    print("完成从用户输入中抽取中医实体")
    await put_think_text_to_msg(user_id, "完成从用户输入中抽取中医实体")
    return state


if __name__ == "__main__":
    import asyncio

    async def main() -> None:
        test_state = {
            "input_semantic_trans": "银翘散可以配金银花吗",
            "history_messages": [],
        }
        result = await extract_entity_from_user_input_node(
            test_state,
            {"configurable": {"thread_id": "test_user"}},
        )
        print(result)

    asyncio.run(main())


