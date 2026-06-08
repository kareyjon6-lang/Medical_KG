from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel
from typing import List, Optional, Union, Literal
from langchain_core.prompts import PromptTemplate
import os
from tqdm import tqdm
import json

from common.llm import my_llm
from common.path_utils import get_file_path
from common.extractor_backend import get_extractor_backend_name

# ======================
# 枚举定义
# ======================
# literal:从多个里面，选择一个
EntityType = Literal["Symptom", "Disease", "Formula", "Herb", "Effect", "Source"]

RelationType = Literal[
    "TREATS_DISEASE",
    "ALLEVIATES_SYMPTOM",
    "HAS_EFFECT",
    "HAS_INGREDIENT",
    "HAS_SYMPTOM",
    "FROM_SOURCE"
]


# ======================
# 属性定义
# ======================
class FormulaAttributes(BaseModel):
    # 别名
    alias: Optional[str] = None
    # 功效
    effect: Optional[str] = None
    # 适应症
    indication: Optional[str] = None
    # 禁忌
    taboo: Optional[str] = None
    # 用法
    usage: Optional[str] = None


class HerbAttributes(BaseModel):
    dosage: Optional[str] = None
    effect: Optional[str] = None
    indication: Optional[str] = None
    meridian: Optional[str] = None
    origin: Optional[str] = None
    place: Optional[str] = None
    processing: Optional[str] = None
    property_flavor: Optional[str] = None
    taboo: Optional[str] = None
    traits: Optional[str] = None


# ======================
# 实体与关系结构
# ======================
class Entity(BaseModel):
    name: str
    type: EntityType
    # Optional: 可选的，（允许为空），本质：Optional[X] 在 Python 中等同于 Union[X, None]。
    # Union: 联合的，联合类型（二选一），要么是A，要么是B
    attributes: Optional[Union[FormulaAttributes, HerbAttributes]] = None
    # “这个函数的返回值有三种可能性：”
    # 一个 FormulaAttributes 对象（成功提取了方剂信息）；
    # 一个 HerbAttributes 对象（成功提取了药材信息）；
    # None（提取失败、输入无效或出现错误）。


class Relation(BaseModel):
    subject: str
    subject_type: EntityType
    relation: RelationType
    object: str
    object_type: EntityType


class TCMKnowledgeGraph(BaseModel):
    entities: List[Entity]
    relations: List[Relation]


"""
{
  "entities": [
    {
      "name": "一品红",
      "type": "Herb",
      "attributes": {
        "alias": "二月红",
        "taboo": "禁止孕妇使用"
      }
    }
  ],
  "relations": [
    {
      "subject": "一品红",
      "subject_type": "Herb",
      "relation": "TREATS_DISEASE",
      "object": "感冒",
      "object_type": "Disease"
    }
  ]
}
"""

# 初始化解析器
parser = JsonOutputParser(pydantic_object=TCMKnowledgeGraph)

prompt = PromptTemplate(
    template=(
        "你是一个中医知识图谱抽取专家。请从以下文本中提取结构化知识：\n"
        "仅当文本中存在实体之间的明确关系时（如‘某方剂治疗某疾病’、‘某药材具有某功效’、‘方剂包含药材’等），才进行抽取。\n"
        "如果文本中仅描述单个实体的信息、未涉及其他实体或关系，请不要抽取，返回空结构：\n"
        "{{\"entities\": [], \"relations\": []}}\n\n"

        "【实体类型说明】\n"
        "- Symptom：症状，如咳嗽、腹痛等\n"
        "- Disease：疾病，如感冒、肺炎、肾虚等\n"
        "- Formula：方剂，如四君子汤、桂枝汤等\n"
        "- Herb：药材，如人参、黄芪、丁香等\n"
        "- Effect：功效，如补气、活血、祛湿、止痛等\n"
        "- Source：出处，如《本草纲目》《伤寒论》等\n\n"

        "【关系类型说明】\n"
        "- TREATS_DISEASE：方剂或药材治疗某种疾病\n"
        "- ALLEVIATES_SYMPTOM：方剂或药材缓解某种症状\n"
        "- HAS_EFFECT：方剂或药材具有某种功效\n"
        "- HAS_INGREDIENT：方剂包含某种药材\n"
        "- HAS_SYMPTOM：疾病包含某种症状\n"
        "- FROM_SOURCE：方剂出自某文献或出处\n\n"

        "若文本涉及方剂或药材，请补充对应的属性字段（如功效、性味、剂量等）。\n"
        "如果文本主要是讲方剂的，请不要抽取药材的属性字段。\n"
        "如果文本主要是讲药材的，请不要抽取方剂的属性字段。\n"
        "如果值为空null，则不必显示键的值。"
        "所有输出必须严格符合以下 JSON 格式：\n"
        "{format_instructions}\n\n"
        "输入文本：{text}"
    ),
    input_variables=["text"],
    partial_variables={"format_instructions": parser.get_format_instructions()}
    # input_variables（输入变量）:
    # 含义：指在调用大模型时，必须动态传入的参数列表。
    # 特点：这些变量在创建模板时还没有具体的值，需要在每次执行（invoke/run）时由用户提供。
    # partial_variables（部分变量 / 预填充变量）:
    # 含义：指在创建模板时，已经预先填入具体值的参数。
    # 特点：这些变量通常是固定的、或者可以通过程序自动生成的（比如格式说明、当前日期、系统指令等）。一旦设置，后续调用时就不需要再传这些值了。
)


# ======================
# 主函数封装
# ======================
def extract_tcm_knowledge(text: str):
    if get_extractor_backend_name() == "local":
        from common.local_extractor import get_local_tcm_extractor

        return get_local_tcm_extractor().extract(text)

    # 构建抽取链（流式输出不经过 parser）
    chain = prompt | my_llm
    
    # 流式输出：使用 for 循环遍历并打印
    full_text = ""
    for chunk in chain.stream({"text": text}):
        # 打印每个 token
        print(chunk.content, end="", flush=True)
        # 拼接完整文本
        full_text += chunk.content
    
    print()  # 换行
    
    # 解析完整文本并返回结果
    return parser.parse(full_text)


def extract_from_folder(folder_path: str, output_json_path: str, fine_tune_json_path: Optional[str] = None):
    """
    遍历文件夹下的所有txt文件，提取知识图谱数据并保存到JSON文件
    支持断点续传：如果输出文件已存在，会跳过已处理的文件
    
    Args:
        folder_path: 输入文件夹路径（包含txt文件）
        output_json_path: 输出JSON文件路径
        fine_tune_json_path: 微调数据JSON文件路径（可选），格式为 [{"instruction":"", "input":"", "output":""}, ...]
        注意：fine_tune_json_path 既是“读取已存在数据”的地址（用于断点续传），也是“保存新生成数据”的地址。
    """
    # 获取文件夹下所有txt文件
    txt_files = []
    for filename in os.listdir(folder_path):
        if filename.endswith('.txt'):
            txt_files.append(os.path.join(folder_path, filename))
    
    if not txt_files:
        print(f"警告：文件夹 {folder_path} 下没有找到txt文件")
        return
    
    # 读取已存在的JSON文件（如果存在），获取已处理的文件列表
    processed_files = set()
    out_list = []
    fine_tune_list = []
    
    # 读取主输出文件
    if os.path.exists(output_json_path):
        try:
            with open(output_json_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                if 'out_list' in existing_data:
                    out_list = existing_data['out_list']
                    # 获取已处理的文件名集合
                    processed_files = {item.get('source_file') for item in out_list if item.get('source_file')}
                    print(f"检测到已存在的输出文件，已处理 {len(processed_files)} 个文件，将继续处理剩余文件...")
        except Exception as e:
            print(f"读取已存在文件时出错: {str(e)}，将重新开始处理")
            out_list = []
            processed_files = set()
    
    # 读取微调数据文件（如果存在）
    if fine_tune_json_path and os.path.exists(fine_tune_json_path):
        try:
            with open(fine_tune_json_path, 'r', encoding='utf-8') as f:
                fine_tune_list = json.load(f)
                if isinstance(fine_tune_list, list):
                    # 检查微调数据数量是否与主输出数据一致
                    if len(fine_tune_list) == len(out_list):
                        print(f"检测到已存在的微调数据文件，已处理 {len(fine_tune_list)} 条数据")
                    else:
                        # 如果数量不一致，保留已有的微调数据，继续处理剩余文件
                        print(f"微调数据文件数量({len(fine_tune_list)})与主输出文件数量({len(out_list)})不一致，将继续处理剩余文件")
                else:
                    fine_tune_list = []
        except Exception as e:
            print(f"读取微调数据文件时出错: {str(e)}，将重新开始处理")
            fine_tune_list = []
    
    # 过滤出未处理的文件
    remaining_files = []
    for txt_file in txt_files:
        filename = os.path.basename(txt_file)
        if filename not in processed_files:
            remaining_files.append(txt_file)
    
    if not remaining_files:
        print(f"所有文件都已处理完成！")
        # 如果还有微调数据需要保存，确保保存
        if fine_tune_json_path and len(fine_tune_list) > 0:
            with open(fine_tune_json_path, 'w', encoding='utf-8') as f:
                json.dump(fine_tune_list, f, ensure_ascii=False, indent=2)
        return
    
    print(f"找到 {len(txt_files)} 个txt文件，其中 {len(remaining_files)} 个待处理，开始处理...")
    
    # 固定instruction
    instruction_text = "请从以下中医文本中抽取知识图谱结构，包括实体与关系。"
    
    # 遍历每个txt文件
    for txt_file in tqdm(remaining_files, desc="处理文件"):
        try:
            # 读取文件内容
            with open(txt_file, 'r', encoding='utf-8') as f:
                text_content = f.read()
            
            # 提取知识图谱数据
            result = extract_tcm_knowledge(text_content)
            result_dict = result
            # 添加文件名信息
            result_dict['source_file'] = os.path.basename(txt_file)
            
            out_list.append(result_dict)
            
            # 构建微调数据
            if fine_tune_json_path:
                # 将结果转换为JSON字符串作为output
                output_json_str = json.dumps(result_dict, ensure_ascii=False, indent=2)
                fine_tune_item = {
                    "instruction": instruction_text,
                    "input": text_content,
                    "output": output_json_str
                }
                fine_tune_list.append(fine_tune_item)
            
            # 每处理完一个文件，立即保存JSON文件
            output_data = {"out_list": out_list}
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            # 保存微调数据文件
            if fine_tune_json_path:
                with open(fine_tune_json_path, 'w', encoding='utf-8') as f:
                    json.dump(fine_tune_list, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            print(f"\n处理文件 {txt_file} 时出错: {str(e)}")
            continue
    
    print(f"\n处理完成！共处理 {len(out_list)} 个文件，结果已保存到: {output_json_path}")
    if fine_tune_json_path:
        print(f"微调数据已保存到: {fine_tune_json_path}")


if __name__ == '__main__':
    # 测试 extract_from_folder 方法
    folder_path = get_file_path("__001__clawer/方剂")
    output_json_path = get_file_path("__002__extract_information/extracted_formula_data.json")
    
    extract_from_folder(folder_path, output_json_path)

"""
为什么这里要加一个微调数据？有什么意义？它是怎么构建出来的
看补充知识第二章
"""
