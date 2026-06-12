import asyncio

from __004__langgraph_more_nodes.nodes import extract_entity_from_user_input_node as node


def test_extract_entity_node_uses_local_tcm_extractor(monkeypatch):
    async def fake_put_think_text_to_msg(user_id, message):
        return None

    def fake_extract_tcm_entities(text):
        assert text == "银翘散可以配金银花吗"
        return {
            "symptoms": [],
            "diseases": [],
            "formulas": ["银翘散"],
            "herbs": ["金银花"],
            "effects": [],
            "sources": [],
        }

    monkeypatch.setattr(node, "put_think_text_to_msg", fake_put_think_text_to_msg)
    monkeypatch.setattr(node, "extract_tcm_entities", fake_extract_tcm_entities)

    state = {"input_semantic_trans": "银翘散可以配金银花吗", "history_messages": []}
    result = asyncio.run(
        node.extract_entity_from_user_input_node(state, {"configurable": {"thread_id": "u1"}})
    )

    assert result["user_input_formulas"] == ["银翘散"]
    assert result["user_input_herbs"] == ["金银花"]
    assert result["user_input_symptoms"] == []
    assert result["user_input_sources"] == []
