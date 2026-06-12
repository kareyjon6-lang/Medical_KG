from typing import Any, Dict, List, TypedDict


class AgentState(TypedDict):
    # 输入
    input: str
    # 当前 LangGraph 运行对应的 job/thread 队列标识
    runtime_thread_id: str
    # 语义转写的input
    input_semantic_trans: str
    # 是否跟中医有关系
    is_zhongyi_intent: bool
    # 直接回答
    direct_out: str
    # 用户输入的实体抽取
    user_input_effects: List[str]
    user_input_diseases: List[str]
    user_input_symptoms: List[str]
    user_input_formulas: List[str]
    user_input_herbs: List[str]
    user_input_sources: List[str]
    # 匹配的实体 （匹配的实体数量是用户输入实体数量的k倍（最多k倍，因为可能还有阈值的影响），因为eg.输入用户实体是头痛，k=3，那么向量匹配为3个，均要加入匹配实体列表中）
    matched_effects: List[str]
    matched_diseases: List[str]
    matched_symptoms: List[str]
    matched_formulas: List[str]
    matched_herbs: List[str]
    matched_sources: List[str]
    # cypher查询语句
    cypher_query: List[str]
    is_all_validate_cypher: bool
    cypher_results: List[Any]
    neo4j_answer: str
    # cypher生成尝试次数
    cypher_generation_attempts: int
    # 历史消息
    history_messages: List[Dict]
    # 输出
    output: str
