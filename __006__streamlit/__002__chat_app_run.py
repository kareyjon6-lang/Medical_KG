import os

from common.path_utils import get_file_path

chat_app_file_path = get_file_path("__006__streamlit/__001__chat_app.py")
os.system(f"streamlit run {chat_app_file_path}")