import streamlit as st
import requests
import json

# 设置页面配置
st.set_page_config(
    page_title="中医药知识图谱聊天助手",
    page_icon="🏥"
)

# 应用标题和描述
st.title("🏥 中医药知识图谱聊天助手")


def get_user_id():
    return "user_001"


def my_assistant_response(input: str):
    api_url = "http://localhost:8000/process"
    request_data = {
        "input": input,
        "user_id": get_user_id()
    }
    # 发送POST请求到FastAPI后端
    response = requests.post(
        api_url,
        json=request_data,
        timeout=180,
        stream=True
    )
    for chunk in response.iter_content(chunk_size=None):
        chunk_str = chunk.decode("utf-8")
        chunk_dict = json.loads(chunk_str)
        yield chunk_dict


def my_assistant_response_request(input: str, st_assistant, st_thinker):
    print("执行request方法")
    assistant_result = ""
    thinker_result = ""
    for chunk_dict in my_assistant_response(input):
        print(chunk_dict)
        type = chunk_dict.get("type", "")
        msg = chunk_dict.get("msg", "")
        if type == "stream":
            assistant_result += msg
            st_assistant.markdown(assistant_result)
        elif type == "think":
            thinker_result += msg
            print(thinker_result)
            st_thinker.markdown(thinker_result)
        elif type == "done":
            st.session_state.messages.append({"role": "assistant", "content": assistant_result, "think": thinker_result})
            # 刷新页面(思考完毕后自动收起思考过程)
            st.rerun()


def show_history_chat_list():
    # 初始化聊天历史
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 显示聊天历史
    for message in st.session_state.messages:
        if message["role"] == "user":
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        elif message["role"] == "assistant":
            with st.chat_message(message["role"]):
                with st.expander("思考完毕", expanded=False):
                    st.markdown(message["think"])
                st.markdown(message["content"])


show_history_chat_list()

if prompt := st.chat_input("请输入您的问题..."):
    with st.chat_message("user"):
        st.markdown(prompt)
        # 添加用户消息到聊天历史
        st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.expander("正在思考中...", expanded=True):
            st_thinker = st.empty()
        st_assistant = st.empty()

    # assistant_response = my_assistant_response(input=prompt)
    # 调用API获取回答
    my_assistant_response_request(prompt, st_assistant, st_thinker)

