"""
将提取的方剂知识图谱数据导入到 Neo4j 数据库
"""
import json
from common.neo4j_manager import neo4j_client
from common.path_utils import get_file_path
from tqdm import tqdm


def import_formula_data_to_neo4j(json_file_path: str, batch_size: int = 100):
    """
    将方剂知识图谱数据导入到 Neo4j
    
    Args:
        json_file_path: JSON 文件路径
        batch_size: 批处理大小，每批处理多少个文件的数据
    """
    print(f"开始读取文件: {json_file_path}")

    # 读取 JSON 文件
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 获取结果列表（可能是 "results" 或 "out_list"）
    if 'results' in data:
        results = data['results']
    elif 'out_list' in data:
        results = data['out_list']
    else:
        # 如果直接是列表
        results = data if isinstance(data, list) else []

    print(f"共找到 {len(results)} 条数据")

    # 统计信息
    total_entities = 0
    total_relations = 0

    # 分批处理
    for i in tqdm(range(0, len(results), batch_size), desc="导入数据到 Neo4j"):
        batch = results[i:i + batch_size]

        # 准备批量操作
        queries_with_params = []

        for item in batch:
            # 获取 extract_dict（可能是 "extract_dict" 或直接是字典）
            if 'extract_dict' in item:
                extract_dict = item['extract_dict']
            else:
                extract_dict = item

            entities = extract_dict.get('entities', [])
            relations = extract_dict.get('relations', [])

            # 添加实体创建操作
            for entity in entities:
                queries_with_params.append((
                    create_entity_cypher(entity),
                    create_entity_params(entity)
                ))
                total_entities += 1

            # 添加关系创建操作
            for relation in relations:
                queries_with_params.append((
                    create_relation_cypher(relation),
                    create_relation_params(relation)
                ))
                total_relations += 1

        # 批量执行
        if queries_with_params:
            neo4j_client.run_multiple_cypher(queries_with_params)

    print(f"\n导入完成！")
    print(f"共导入 {total_entities} 个实体，{total_relations} 个关系")


def create_entity_cypher(entity):
    """生成创建实体的 Cypher 语句"""
    entity_type = entity.get('type', 'Entity')
    return f"""
    MERGE (n:{entity_type} {{name: $name}})
    SET n += $props
    """


def create_entity_params(entity):
    """生成创建实体的参数"""
    entity_name = entity.get('name')
    entity_type = entity.get('type')
    attributes = entity.get('attributes', {})

    props = {'name': entity_name}
    if attributes:
        for key, value in attributes.items():
            if value is not None and value != '':
                props[key] = value

    return {'name': entity_name, 'props': props}


def create_relation_cypher(relation):
    """生成创建关系的 Cypher 语句"""
    subject_type = relation.get('subject_type', 'Entity')
    relation_type = relation.get('relation', 'RELATED_TO')
    object_type = relation.get('object_type', 'Entity')

    return f"""
    MATCH (a:{subject_type} {{name: $subject}})
    MATCH (b:{object_type} {{name: $object}})
    MERGE (a)-[r:{relation_type}]->(b)
    """


def create_relation_params(relation):
    """生成创建关系的参数"""
    return {
        'subject': relation.get('subject'),
        'object': relation.get('object')
    }


if __name__ == '__main__':
    # 方剂数据文件路径
    json_file_path = get_file_path("__002__extract_information/extract_formula_data.json")
    import_formula_data_to_neo4j(json_file_path, batch_size=100)
    # 中药数据文件路径
    json_file_path = get_file_path("__002__extract_information/extract_herb_data.json")
    import_formula_data_to_neo4j(json_file_path, batch_size=100)

    # print("=" * 50)
    # print("开始将方剂知识图谱数据导入到 Neo4j")
    # print("=" * 50)
    #
    # # 导入数据（每批处理 100 个文件的数据）
    # import_formula_data_to_neo4j(json_file_path, batch_size=100)
    #
    # print("=" * 50)
    # print("导入完成")
    # print("=" * 50)
