from typing import Any, Mapping, Optional

from langchain_core.runnables import RunnableConfig


def get_thread_id(config: RunnableConfig | None = None, state: Optional[Mapping[str, Any]] = None) -> str:
    configurable = (config or {}).get("configurable") or {}
    if configurable.get("thread_id"):
        return str(configurable.get("thread_id") or "")
    if state and state.get("runtime_thread_id"):
        return str(state.get("runtime_thread_id") or "")
    return ""

