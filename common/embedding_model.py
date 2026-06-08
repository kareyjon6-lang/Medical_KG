from sentence_transformers import SentenceTransformer
from common.config import Config

conf = Config()

embedding_model = SentenceTransformer(conf.EMBEDDING_MODEL_PATH)
# SentenceTransformer 是通用万能的文本向量化底层库（支持所有模型、所有向量库）；
# BGEM3EmbeddingFunction 是 Milvus 官方专为 BGE-M3 模型封装的简化工具（专用、绑定 Milvus、底层还是调用了前者）。
