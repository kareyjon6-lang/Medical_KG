import re


class CypherGuardError(ValueError):
    """Raised when a Cypher query is not safe for public read endpoints."""


_FORBIDDEN_KEYWORDS = {
    "CALL",
    "CREATE",
    "DELETE",
    "DETACH",
    "DROP",
    "LOAD",
    "MERGE",
    "REMOVE",
    "SET",
}


def ensure_read_only_cypher(query):
    normalized = " ".join((query or "").strip().split())
    if not normalized:
        raise CypherGuardError("Cypher query is empty.")

    if ";" in normalized:
        raise CypherGuardError("Only one Cypher statement is allowed.")

    upper_query = normalized.upper()
    tokens = set(re.findall(r"[A-Z_]+", upper_query))
    blocked = tokens.intersection(_FORBIDDEN_KEYWORDS)
    if blocked:
        raise CypherGuardError("Cypher query contains write or admin keywords.")

    if not upper_query.startswith("MATCH ") or " RETURN " not in upper_query:
        raise CypherGuardError("Only MATCH ... RETURN read queries are allowed.")

    return normalized
