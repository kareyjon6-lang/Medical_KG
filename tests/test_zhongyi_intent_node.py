import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE_FILE = ROOT / "__004__langgraph_more_nodes" / "nodes" / "zhongyi_intent_node.py"


def load_local_intent_helpers():
    source = NODE_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(NODE_FILE))
    wanted_assignments = {
        "TCM_DIRECT_KEYWORDS",
        "TCM_FORMULA_SUFFIXES",
        "TCM_SYMPTOM_KEYWORDS",
        "TCM_HELP_HINTS",
        "TCM_BODY_PAIN_PATTERN",
    }
    wanted_functions = {"looks_like_tcm_symptom_question", "infer_tcm_intent_fast"}
    selected_nodes = [ast.Import(names=[ast.alias(name="re")])]
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in wanted_assignments for target in node.targets):
            selected_nodes.append(node)
        if isinstance(node, ast.FunctionDef) and node.name in wanted_functions:
            selected_nodes.append(node)
    module = ast.fix_missing_locations(ast.Module(body=selected_nodes, type_ignores=[]))
    namespace = {"re": re}
    exec(compile(module, str(NODE_FILE), "exec"), namespace)
    return namespace["looks_like_tcm_symptom_question"], namespace["infer_tcm_intent_fast"]


def test_fast_intent_marks_common_symptom_help_queries_as_tcm_related():
    looks_like_tcm_symptom_question, infer_tcm_intent_fast = load_local_intent_helpers()

    assert looks_like_tcm_symptom_question("我腰疼，我该怎么办") is True
    assert infer_tcm_intent_fast("我腰疼，我该怎么办") is True


def test_fast_intent_preserves_non_medical_queries_as_unknown():
    looks_like_tcm_symptom_question, infer_tcm_intent_fast = load_local_intent_helpers()

    assert looks_like_tcm_symptom_question("帮我写一个 Python 排序函数") is False
    assert infer_tcm_intent_fast("帮我写一个 Python 排序函数") is None
