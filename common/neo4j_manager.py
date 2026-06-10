# pip install neo4j
import json

from common.config import Config

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None


conf = Config()


class Neo4jUnavailableError(RuntimeError):
    pass


class UnavailableNeo4jClient:
    def __init__(self, reason: str):
        self.reason = reason

    def _raise(self):
        raise Neo4jUnavailableError(self.reason)

    def run_cypher(self, query, parameters=None):
        self._raise()

    def run_multiple_cypher(self, queries_with_params):
        self._raise()

    def export_tcm_metadata_to_json(self, output_path="tcm_metadata.json"):
        self._raise()

    def get_all_node_names(self, label: str = None):
        self._raise()

    def validate_cypher(self, query: str) -> bool:
        self._raise()


class Neo4jClient:
    def __init__(self, uri, user, password):
        if GraphDatabase is None:
            raise Neo4jUnavailableError("The 'neo4j' package is not installed.")
        if not uri or not user:
            raise Neo4jUnavailableError("Neo4j configuration is incomplete.")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def __del__(self):
        if getattr(self, "driver", None) is not None:
            self.driver.close()

    def run_cypher(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def run_multiple_cypher(self, queries_with_params):
        with self.driver.session() as session:
            def transaction_logic(tx):
                for query, params in queries_with_params:
                    tx.run(query, params or {})

            session.execute_write(transaction_logic)

    def export_tcm_metadata_to_json(self, output_path="tcm_metadata.json"):
        with self.driver.session() as session:
            label_query = """
            MATCH (n)
            UNWIND labels(n) AS label
            RETURN DISTINCT label
            """
            labels = [record["label"] for record in session.run(label_query)]

            rel_query = """
            MATCH (n)-[r]-()
            RETURN DISTINCT type(r) AS rel_type
            """
            rel_types = [record["rel_type"] for record in session.run(rel_query)]

            triple_query = """
            MATCH (n)-[r]->(m)
            WITH head(labels(n)) AS from_label, type(r) AS rel_type, head(labels(m)) AS to_label
            RETURN DISTINCT from_label, rel_type, to_label
            """
            triples = [
                {
                    "from": record["from_label"],
                    "rel_type": record["rel_type"],
                    "to": record["to_label"],
                    "description": "",
                }
                for record in session.run(triple_query)
            ]

            node_props_query = """
            MATCH (n)
            UNWIND labels(n) AS label
            UNWIND keys(n) AS prop
            RETURN DISTINCT label, prop
            ORDER BY label, prop
            """
            label_props = {}
            for record in session.run(node_props_query):
                label = record["label"]
                prop = record["prop"]
                if prop == "project":
                    continue
                label_props.setdefault(label, []).append({"name": prop, "description": ""})

            rel_props_query = """
            MATCH (n)-[r]->(m)
            UNWIND keys(r) AS prop
            RETURN DISTINCT type(r) AS rel_type, prop
            ORDER BY rel_type, prop
            """
            rel_type_props = {}
            for record in session.run(rel_props_query):
                rel_type = record["rel_type"]
                prop = record["prop"]
                rel_type_props.setdefault(rel_type, []).append({"name": prop, "description": ""})

            json_obj = {
                "labels": [
                    {
                        "name": label,
                        "description": "",
                        "properties": label_props.get(label, []),
                    }
                    for label in labels
                ],
                "relationships": [
                    {
                        "type": rel,
                        "description": "",
                        "properties": rel_type_props.get(rel, []),
                    }
                    for rel in rel_types
                ],
                "triples": triples,
            }

            with open(output_path, "w", encoding="utf-8") as file_obj:
                json.dump(json_obj, file_obj, ensure_ascii=False, indent=2)

            return output_path

    def get_all_node_names(self, label: str = None):
        if label is None:
            query = """
            MATCH (n)
            RETURN DISTINCT n.name AS name
            ORDER BY name
            """
        else:
            query = f"""
            MATCH (n:{label})
            RETURN DISTINCT n.name AS name
            ORDER BY name
            """
        with self.driver.session() as session:
            result = session.run(query)
            return [record["name"] for record in result if record["name"]]

    def validate_cypher(self, query: str) -> bool:
        try:
            with self.driver.session() as session:
                session.run(f"EXPLAIN {query}")
            return True
        except Exception:
            return False


def create_neo4j_client():
    try:
        return Neo4jClient(conf.NEO4J_URI, conf.NEO4J_USER, conf.NEO4J_PASSWORD)
    except Exception as exc:
        return UnavailableNeo4jClient(str(exc))


neo4j_client = create_neo4j_client()
