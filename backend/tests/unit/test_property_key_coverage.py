"""Drift guard: node/edge properties the reviewer pipeline reads vs. what the model may send.

Structured Outputs rejects a free-form object, so ``strict_schema`` has to enumerate the property
keys (Task 1 probe). That enumeration is a second copy of knowledge already expressed by the gate
and the lens — and a key missing from it is invisible rather than loud: the model is structurally
unable to emit the property, the extraction still looks obedient, and the reviewer simply never
sees an antagonism labelled as one.

Backend may import ingestion, never the reverse, so the check lives here.
"""

import inspect
import re

from app.graph import back_translation, engineer_gate

from ingestion.extract.strict_schema import EDGE_PROPERTY_KEYS, NODE_PROPERTY_KEYS


def _keys_read(module) -> set[str]:
    """Property keys read on any line that touches a properties bag."""
    found: set[str] = set()
    for line in inspect.getsource(module).splitlines():
        if "props" in line or '"properties"' in line:
            found.update(re.findall(r'\.get\("(\w+)"\)', line))
    found.discard("properties")  # the bag itself, not a key inside it
    return found


def test_every_property_key_the_pipeline_reads_can_be_emitted():
    declared = set(NODE_PROPERTY_KEYS) | set(EDGE_PROPERTY_KEYS)
    read = _keys_read(engineer_gate) | _keys_read(back_translation)

    assert read, "掃不到任何屬性讀取,守衛的前提已失效"
    assert read <= declared, (
        f"gate/lens 讀得到、但 strict schema 沒宣告因而模型送不出來的屬性:{sorted(read - declared)}"
    )
