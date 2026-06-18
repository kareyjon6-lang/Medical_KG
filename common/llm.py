import asyncio
import os
import threading

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from common.config import Config

conf = Config()

# ============ 配置llm区域 ============
my_llm = ChatOpenAI(
    api_key=conf.MODEL_API_KEY,
    base_url=conf.MODEL_BASE_URL,
    model=conf.MODEL_NAME,
)


def _get_llm_api_concurrency() -> int:
    value = os.getenv("LLM_API_CONCURRENCY", "3")
    try:
        parsed = int(value)
    except ValueError:
        parsed = 3
    return max(1, parsed)


LLM_API_CONCURRENCY = _get_llm_api_concurrency()
_llm_capacity = threading.BoundedSemaphore(LLM_API_CONCURRENCY)


async def _acquire_llm_slot() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _llm_capacity.acquire)


async def llm_ainvoke(messages, **kwargs):
    await _acquire_llm_slot()
    try:
        return await my_llm.ainvoke(messages, **kwargs)
    finally:
        _llm_capacity.release()


async def llm_astream(messages, **kwargs):
    await _acquire_llm_slot()
    try:
        async for chunk in my_llm.astream(messages, **kwargs):
            yield chunk
    finally:
        _llm_capacity.release()


async def llm_runnable_astream(runnable, input_value, **kwargs):
    await _acquire_llm_slot()
    try:
        async for chunk in runnable.astream(input_value, **kwargs):
            yield chunk
    finally:
        _llm_capacity.release()


if __name__ == '__main__':
    # 测试大模型用户输入
    print(my_llm([HumanMessage(content="你好")]))
