"""
给知识图谱中实体名字进行向量化存储，用户输入的实体进行向量数据库的检索
FAISS 向量存储 Demo
接收文本列表，使用 embedding 模型转换为向量，存储到 FAISS 索引中，
普通方药增删主链路不应默认调用这里的全量重建逻辑。
这里的脚本职责更偏向初始化索引和离线维护，而不是实时问答接口。
"""
import numpy as np
import faiss
import pickle
from typing import List
from common.config import Config
from common.embedding_model import embedding_model
from common.neo4j_manager import neo4j_client

conf = Config()

# 索引文件路径
INDEX_PATH = conf.ENTITY_INDEX_PATH
ID2TEXT_PATH = conf.ENTITY_ID2TEXT_PATH


def text_to_embeddings(texts: List[str]) -> np.ndarray:
    """
    将文本列表转换为 embedding 向量

    Args:
        texts: 文本列表

    Returns:
        numpy array, shape (n, dimension) - 向量数组
    """
    model = embedding_model
    print(f"正在将 {len(texts)} 个文本转换为向量...")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    print(f"向量转换完成！向量形状: {embeddings.shape}")
    return embeddings.astype('float32')


def create_index(dimension: int):
    """
    创建 FAISS 索引
    使用 L2 距离（欧氏距离）的 IndexFlatL2

    Args:
        dimension: 向量维度
    """
    # IndexFlatL2 使用 L2 距离（欧氏距离）进行精确搜索
    index = faiss.IndexFlatL2(dimension)
    return index


def store_texts(texts: List[str], index_path: str = INDEX_PATH, id2text_path: str = ID2TEXT_PATH):
    """
    将文本列表存储到 FAISS 索引

    Args:
        texts: 文本列表
        index_path: 索引文件保存路径
        id2text_path: ID到文本映射文件保存路径

    Returns:
        faiss.Index: 创建的索引对象
    """
    """
        距离公式：
        1、IP：内积
        2、欧式距离：两点连线的长度，L2距离
        3、余弦相似度
        4、曼哈顿距离：L1距离
        5、杰卡德相似度：交集/并集，计算速度很快
        6、编辑距离：一个文本通过（删除添加修改）字符达到另一个文本的操作次数
    """
    # 1、将文本转换为向量
    print("\n1. 将文本转换为向量...")
    vectors = text_to_embeddings(texts)

    # 2、归一化向量（提高搜索效果）
    print("\n2. 归一化向量...")
    faiss.normalize_L2(vectors)

    # 3、创建索引
    print("\n3. 创建 FAISS 索引...")
    index = create_index(vectors.shape[1])

    # 4、添加向量到索引
    print(f"\n4. 添加 {len(vectors)} 个向量到索引...")
    index.add(vectors)
    print(f"索引中向量数量: {index.ntotal}")

    # 5、保存索引
    print(f"\n5. 保存索引到: {index_path}")
    faiss.write_index(index, index_path)
    print("索引保存成功！")

    # 6、保存 id2text 映射
    id2text = {i: text for i, text in enumerate(texts)}
    with open(id2text_path, 'wb') as f:
        pickle.dump(id2text, f)
    print(f"ID到文本的映射已保存到: {id2text_path}")

    return index


def main():
    # 示例文本列表（用户可以修改这里）
    # texts = [
    #     "人参具有补气养血的功效",
    #     "黄芪可以增强免疫力",
    #     "当归常用于治疗妇科疾病",
    #     "四君子汤由人参、白术、茯苓、甘草组成",
    #     "感冒是常见的呼吸道疾病",
    #     "咳嗽是感冒的常见症状",
    #     "桂枝汤出自《伤寒论》",
    #     "中医强调辨证论治",
    #     "针灸是中医的重要治疗方法",
    #     "中药需要根据体质选择"
    # ]
    # 获取所有节点名称
    names = neo4j_client.get_all_node_names()
    # 存储文本列表
    store_texts(names)


if __name__ == "__main__":
    main()
