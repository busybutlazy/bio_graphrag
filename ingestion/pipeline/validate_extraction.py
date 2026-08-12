import json
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "extraction_output_schema.json"
_schema = json.loads(SCHEMA_PATH.read_text())


def validate_extraction_output(candidate: dict) -> None:
    jsonschema.validate(instance=candidate, schema=_schema)


def _element_schema(name: str) -> dict:
    """The same rules, scoped to one element.

    ``$defs`` rides along so the internal ``#/$defs/node_type`` references still resolve — the
    element definition is not self-contained. Building a new outer dict never touches ``_schema``,
    which is cached here and is also what ``engineer_gate`` judges hand-made proposals against.
    """
    return {**_schema["$defs"][name], "$defs": _schema["$defs"]}


_NODE_SCHEMA = _element_schema("node")
_EDGE_SCHEMA = _element_schema("edge")


def validate_node(node: dict) -> None:
    jsonschema.validate(instance=node, schema=_NODE_SCHEMA)


def validate_edge(edge: dict) -> None:
    jsonschema.validate(instance=edge, schema=_EDGE_SCHEMA)
