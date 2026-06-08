import os

from dotenv import load_dotenv

from common.path_utils import get_file_path

load_dotenv(get_file_path(".env"))


class Config:
    def __init__(self):
        self.MODEL_API_KEY = os.getenv("MODEL_API_KEY")
        self.MODEL_BASE_URL = os.getenv("MODEL_BASE_URL")
        self.MODEL_NAME = os.getenv("MODEL_NAME")

        self.NEO4J_URI = os.getenv("NEO4J_URI")
        self.NEO4J_USER = os.getenv("NEO4J_USER")
        self.NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

        self.TCM_METADATA = open(
            get_file_path("__003__create_neo4j_database/tcm_metadata.json"),
            "r",
            encoding="utf-8",
        ).read()

        self.EMBEDDING_MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH")
        self.ENTITY_INDEX_PATH = get_file_path("__003__create_neo4j_database/nero4j_embedding_faiss.index")
        self.ENTITY_ID2TEXT_PATH = get_file_path("__003__create_neo4j_database/nero4j_embedding_faiss_id2text.pkl")
        self.HISTORY_NUM = 5


if __name__ == "__main__":
    conf = Config()
    print(conf.TCM_METADATA)
