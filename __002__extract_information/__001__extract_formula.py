"""
抽取方剂知识图谱数据
"""
from __002__extract_information.__000__extract_graph_data_utils import extract_from_folder
from common.path_utils import get_file_path

if __name__ == '__main__':
    # 方剂文件夹路径
    folder_path = get_file_path("__001__clawer/方剂")
    # 输出JSON文件路径
    output_json_path = get_file_path("__002__extract_information/extract_formula_data.json")
    # 微调数据JSON文件路径
    fine_tune_json_path = get_file_path("__002__extract_information/extract_formula_finetune_data.json")
    
    print("=" * 50)
    print("开始抽取方剂知识图谱数据")
    print("=" * 50)
    
    extract_from_folder(folder_path, output_json_path, fine_tune_json_path)
    
    print("=" * 50)
    print("方剂知识图谱数据抽取完成")
    print("=" * 50)

