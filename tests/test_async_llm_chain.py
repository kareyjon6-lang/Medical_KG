from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


LLM_NODE_FILES = [
    ROOT / "__004__langgraph_more_nodes" / "nodes" / "semantic_transcription_node.py",
    ROOT / "__004__langgraph_more_nodes" / "nodes" / "zhongyi_intent_node.py",
    ROOT / "__004__langgraph_more_nodes" / "nodes" / "generate_neo4j_cypher_node.py",
    ROOT / "__004__langgraph_more_nodes" / "nodes" / "neo4j_answer_generate_node.py",
    ROOT / "__004__langgraph_more_nodes" / "nodes" / "llm_direct_out_node.py",
]


def test_llm_adapter_exposes_async_concurrency_helpers():
    source = (ROOT / "common" / "llm.py").read_text(encoding="utf-8")

    assert "LLM_API_CONCURRENCY" in source
    assert "LLM_API_TIMEOUT_SECONDS" in source
    assert "LLM_API_STREAM_IDLE_TIMEOUT_SECONDS" in source
    assert "async def llm_ainvoke" in source
    assert "async def llm_astream" in source
    assert "asyncio.wait_for" in source


def test_langgraph_llm_nodes_do_not_call_sync_llm_methods_directly():
    for path in LLM_NODE_FILES:
        source = path.read_text(encoding="utf-8")

        assert "my_llm.invoke" not in source, path
        assert "my_llm.stream" not in source, path
