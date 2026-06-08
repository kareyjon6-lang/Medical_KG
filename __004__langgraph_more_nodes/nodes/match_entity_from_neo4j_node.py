"""
FAISS 向量搜索 Demo
接收一个文本，使用 embedding 模型转换为向量，搜索最相似的 top3 文本
"""
import numpy as np
import faiss
import pickle
import os
from langchain_core.runnables import RunnableConfig

from sentence_transformers import SentenceTransformer

from __004__langgraph_more_nodes.agent_state import AgentState
from common.config import Config
from common.embedding_model import embedding_model
from common.path_utils import get_file_path
from __005__fastapi.__003__msg_queue import put_think_text_to_msg

conf = Config()
# 索引文件路径
INDEX_PATH = conf.ENTITY_INDEX_PATH
ID2TEXT_PATH = conf.ENTITY_ID2TEXT_PATH


def text_to_embedding(text: str) -> np.ndarray:
    """
    将单个文本转换为 embedding 向量

    Args:
        text: 输入文本

    Returns:
        numpy array, shape (dimension,) - 向量
    """
    model = embedding_model
    embedding = model.encode([text], convert_to_numpy=True)[0]
    return embedding.astype('float32')


def load_index(index_path: str = INDEX_PATH):
    """
    加载 FAISS 索引

    Args:
        index_path: 索引文件路径

    Returns:
        faiss.Index: 加载的索引对象
    """

    print(f"正在加载索引: {index_path}")
    index = faiss.read_index(index_path)
    return index


def load_id2text(id2text_path: str = ID2TEXT_PATH):
    """
    加载 ID 到文本的映射

    Args:
        id2text_path: 映射文件路径

    Returns:
        dict: ID 到文本的映射字典
    """

    print(f"正在加载 ID 到文本的映射: {id2text_path}")
    with open(id2text_path, 'rb') as f:
        id2text = pickle.load(f)
    print(f"映射加载成功！包含 {len(id2text)} 个条目")

    return id2text


def search_similar_texts(index: faiss.Index, query_text: str, k: int = 3):
    """
    搜索最相似的文本

    Args:
        index: FAISS 索引对象
        query_text: 查询文本
        k: 返回最相似的 k 个文本（默认3）

    Returns:
        distances: 距离数组，shape (k,)
        indices: 索引数组，shape (k,)
    """
    # 将查询文本转换为向量
    query_vector = text_to_embedding(query_text)

    # 归一化查询向量（与存储时的归一化保持一致）
    query_vector = query_vector.reshape(1, -1)
    # 归一化向量
    faiss.normalize_L2(query_vector)

    # 搜索
    distances, indices = index.search(query_vector, k)

    return distances[0], indices[0]


def search_with_threshold(index: faiss.Index, query_text: str, k: int = 3, threshold: float = 0.5,
                          id2text: dict = None):
    """
    搜索最相似文本，返回 top-k 中相似度 >= 阈值的结果

    Args:
        index: FAISS 索引
        query_text: 查询文本
        k: top-k 数量
        threshold: 相似度阈值
        id2text: 映射字典

    Returns:
        filtered_results: list, Top-k 中满足阈值的结果
    """
    distances, indices = search_similar_texts(index, query_text, k)

    filtered_results = []

    for dist, idx in zip(distances, indices):
        similarity = 1 / (1 + dist)
        if similarity >= threshold:
            filtered_results.append({
                "id": int(idx),
                "distance": float(dist),
                "similarity": float(similarity),
                "text": id2text.get(int(idx), "未知文本")
            })

    return filtered_results


def display_results(query_text: str, distances: np.ndarray, indices: np.ndarray, id2text: dict = None):     # 目前没用到
    """
    显示搜索结果

    Args:
        query_text: 查询文本
        distances: 距离数组
        indices: 索引数组
        id2text: ID 到文本的映射（可选）
    """
    print(f"查询文本: {query_text}")
    print(f"\n找到 {len(distances)} 个相似文本（Top {len(distances)}）:")

    for i, (distance, idx) in enumerate(zip(distances, indices), 1):
        print(f"\n排名 {i}:")
        print(f"  相似度分数: {1 / (1 + distance):.4f}")  # 将距离转换为相似度分数
        print(f"  距离: {distance:.6f}")
        print(f"  文本: {id2text.get(idx, '未知文本')}")


def search_text(query_text: str, k: int = 3):       # 目前没用到
    """
    搜索相似文本的主函数

    Args:
        query_text: 查询文本
        k: 返回最相似的 k 个文本（默认3）
    """
    # 1、加载索引
    print("\n1. 加载 FAISS 索引文件...")
    index = load_index()

    # 2、加载 ID 到文本的映射
    print("\n2. 加载 ID 到文本的映射...")
    id2text = load_id2text()

    # 3、搜索相似文本
    print(f"\n3. 搜索与 '{query_text}' 最相似的 {k} 个文本...")
    distances, indices = search_similar_texts(index, query_text, k)

    # 4、显示结果
    display_results(query_text, distances, indices, id2text)

    return distances, indices, id2text


zhongyi_index = load_index()
zhongyi_id2text = load_id2text()


def match_entity_neo4j(state: AgentState, user_input_key, matched_key):
    user_input_entitys = state.get(user_input_key, "")
    matched_entitys = []
    for user_input in user_input_entitys:
        results = search_with_threshold(zhongyi_index, user_input, k=3, threshold=0.6, id2text=zhongyi_id2text)
        for result in results:
            matched_entitys.append(result["text"])
    state[matched_key] = matched_entitys


async def match_entity_from_neo4j_node(state: AgentState, config: RunnableConfig):
    # 获取用户ID
    user_id = config.get("configurable", {}).get("thread_id", "")
    print("开始匹配实体")
    await put_think_text_to_msg(user_id, "开始匹配知识图谱中的实体")
    match_entity_neo4j(state, "user_input_effects", "matched_effects")
    match_entity_neo4j(state, "user_input_diseases", "matched_diseases")
    match_entity_neo4j(state, "user_input_symptoms", "matched_symptoms")
    match_entity_neo4j(state, "user_input_formulas", "matched_formulas")
    match_entity_neo4j(state, "user_input_herbs", "matched_herbs")
    match_entity_neo4j(state, "user_input_sources", "matched_sources")
    await put_think_text_to_msg(user_id, "完成匹配知识图谱中的实体")
    return state


if __name__ == '__main__':
    from langchain_core.runnables import RunnableConfig
    import asyncio


    async def main():
        config = RunnableConfig(configurable={"thread_id": "test_user"})
        test_state = {
            "user_input_symptoms": ["脑袋疼"]
        }
        result = await match_entity_from_neo4j_node(test_state, config)
        print(result)


    asyncio.run(main())