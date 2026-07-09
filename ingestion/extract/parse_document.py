"""Read a chapter source file into document metadata + body text.

Source format (locked with the user): a markdown file with a flat YAML-style
front-matter block delimited by ``---`` lines::

    ---
    doc_id: doc:endocrine:thyroid
    title: 甲狀腺與代謝調節
    topic: thyroid_regulation
    grade_level: 高二
    source_type: textbook
    extraction_profile: endocrine
    ---
    # 甲狀腺
    正文…

Real chapters live under ``data/private/chapters/`` (gitignored IP); a public
demo chapter ships under ``data/sample/chapters/``. Front-matter here is always
flat scalars, so we parse it directly and avoid adding a YAML dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_FENCE = "---"


class DocumentParseError(ValueError):
    pass


@dataclass
class ParsedDocument:
    doc_id: str
    title: str
    body: str
    topic: str | None = None
    grade_level: str | None = None
    source_type: str | None = None
    extraction_profile: str | None = None

    def document_row(self) -> dict:
        """The dict shape ``load_postgres.upsert_documents`` expects."""
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "topic": self.topic,
            "grade_level": self.grade_level,
            "source_type": self.source_type,
        }


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Split ``---`` front-matter from the body; return ``(meta, body)``.

    A file with no leading ``---`` fence is treated as all body, empty meta.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return {}, text.strip()

    meta: dict = {}
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
            body = "\n".join(lines[i + 1 :]).strip()
            return meta, body
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise DocumentParseError(f"front-matter line is not `key: value`: {line!r}")
        meta[key.strip()] = value.strip().strip("'\"")
    raise DocumentParseError("front-matter opened with `---` but never closed")


def parse_document(path: str | Path) -> ParsedDocument:
    path = Path(path)
    if not path.exists():
        raise DocumentParseError(f"source file not found: {path}")
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))

    doc_id = meta.get("doc_id") or f"doc:{path.stem}"
    title = meta.get("title") or path.stem
    if not body.strip():
        raise DocumentParseError(f"{path} has no body text to ingest")

    return ParsedDocument(
        doc_id=doc_id,
        title=title,
        body=body,
        topic=meta.get("topic"),
        grade_level=meta.get("grade_level"),
        source_type=meta.get("source_type"),
        extraction_profile=meta.get("extraction_profile"),
    )
