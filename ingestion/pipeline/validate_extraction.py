import json
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "extraction_output_schema.json"
_schema = json.loads(SCHEMA_PATH.read_text())


def validate_extraction_output(candidate: dict) -> None:
    jsonschema.validate(instance=candidate, schema=_schema)
