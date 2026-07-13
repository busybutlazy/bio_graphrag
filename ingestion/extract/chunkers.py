"""Chunking strategies for document ingestion.

Three deterministic strategies share one interface (``chunk(text) -> list[str]``)
so the ingest runner and the admin API can switch between them by name:

- ``fixed``           : hard character windows with overlap.
- ``recursive``       : split on a separator hierarchy, greedily merge to size.
- ``markdown_header`` : split on markdown/HTML headers, oversized sections fall
                        back to ``recursive``.

Kept dependency-free on purpose (no langchain) — see the résumé-minimalism note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 80
DEFAULT_MAX_SECTION_SIZE = 800
DEFAULT_MIN_CHUNK_SIZE = 50

# Separator hierarchy for recursive splitting: try to break on the most
# semantic boundary first (blank line = paragraph), degrade to finer ones.
_RECURSIVE_SEPARATORS = ["\n\n", "\n", "。", "!", "?", ".", " "]

# A markdown ATX header (``# ``…``### ``) or an HTML h1–h3 open tag at line start.
_HEADER_RE = re.compile(
    r"^(?:#{1,3}\s+.*|<h[1-3][^>]*>.*)$",
    re.IGNORECASE,
)


class Chunker:
    """Base interface. Subclasses implement ``chunk``."""

    #: strategy name as exposed in the API / job stats.
    name: str = ""

    def chunk(self, text: str) -> list[str]:  # pragma: no cover - abstract
        raise NotImplementedError

    def params(self) -> dict:  # pragma: no cover - trivial
        return {}


@dataclass
class FixedChunker(Chunker):
    """Slide a fixed-size character window with a fixed overlap."""

    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    name: str = "fixed"

    def __post_init__(self) -> None:
        _validate_size_overlap(self.chunk_size, self.chunk_overlap)

    def chunk(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        step = self.chunk_size - self.chunk_overlap
        starts = list(range(0, len(text), step))
        # Drop a trailing window whose span is already fully covered by the
        # previous one (its content would be pure overlap). Positional check,
        # not substring containment — repetitive text must not lose coverage.
        if len(starts) >= 2 and starts[-2] + self.chunk_size >= len(text):
            starts.pop()
        chunks = [text[s : s + self.chunk_size] for s in starts]
        return [c.strip() for c in chunks if c.strip()]

    def params(self) -> dict:
        return {"chunk_size": self.chunk_size, "chunk_overlap": self.chunk_overlap}


@dataclass
class RecursiveChunker(Chunker):
    """Split on a separator hierarchy, then greedily merge pieces up to size.

    Mirrors the "paragraph-first, size-controlled" spirit of the reference
    orchestrator without pulling in a splitting library.
    """

    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE
    name: str = "recursive"

    def __post_init__(self) -> None:
        _validate_size_overlap(self.chunk_size, self.chunk_overlap)
        if self.min_chunk_size < 0 or self.min_chunk_size >= self.chunk_size:
            raise ValueError("min_chunk_size must be in [0, chunk_size)")

    def chunk(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        pieces = self._split(text, 0)
        return self._merge(pieces)

    def _split(self, text: str, sep_index: int) -> list[str]:
        """Break text into atoms no larger than chunk_size, preserving content.

        Concatenating the returned atoms reproduces ``text`` exactly: when we
        split on a separator we reattach it to every part but the last, so no
        character is added or dropped.
        """
        if len(text) <= self.chunk_size:
            return [text]
        if sep_index >= len(_RECURSIVE_SEPARATORS):
            # No separator left: hard-cut the oversized run into size windows.
            return [
                text[i : i + self.chunk_size]
                for i in range(0, len(text), self.chunk_size)
            ]
        sep = _RECURSIVE_SEPARATORS[sep_index]
        if sep not in text:
            return self._split(text, sep_index + 1)
        parts = text.split(sep)
        atoms: list[str] = []
        for i, part in enumerate(parts):
            piece = part + (sep if i < len(parts) - 1 else "")
            if piece == "":
                continue
            if len(piece) <= self.chunk_size:
                atoms.append(piece)
            else:
                atoms.extend(self._split(piece, sep_index + 1))
        return atoms

    def _merge(self, atoms: list[str]) -> list[str]:
        chunks: list[str] = []
        current = ""
        for atom in atoms:
            if current and len(current) + len(atom) > self.chunk_size:
                chunks.append(current.strip())
                current = _tail(current, self.chunk_overlap) + atom
            else:
                current += atom
        if current.strip():
            tail = current.strip()
            if chunks and len(tail) < self.min_chunk_size:
                chunks[-1] = (chunks[-1] + " " + tail).strip()
            else:
                chunks.append(tail)
        return [c for c in chunks if c]

    def params(self) -> dict:
        return {
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "min_chunk_size": self.min_chunk_size,
        }


@dataclass
class MarkdownHeaderChunker(Chunker):
    """One chunk per ``#``/``##``/``###`` (or HTML h1–h3) section.

    A section that exceeds ``max_section_size`` is further split by the
    recursive strategy so no single chunk blows past the size budget.
    """

    max_section_size: int = DEFAULT_MAX_SECTION_SIZE
    name: str = "markdown_header"

    def __post_init__(self) -> None:
        if self.max_section_size <= 0:
            raise ValueError("max_section_size must be positive")

    def chunk(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        sections = self._split_sections(text)
        fallback = RecursiveChunker(chunk_size=self.max_section_size)
        chunks: list[str] = []
        for section in sections:
            if len(section) <= self.max_section_size:
                chunks.append(section)
            else:
                chunks.extend(fallback.chunk(section))
        return [c.strip() for c in chunks if c.strip()]

    @staticmethod
    def _split_sections(text: str) -> list[str]:
        sections: list[str] = []
        current: list[str] = []
        for line in text.splitlines():
            if _HEADER_RE.match(line.strip()) and current:
                sections.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append("\n".join(current))
        return sections

    def params(self) -> dict:
        return {"max_section_size": self.max_section_size}


_STRATEGIES = {
    "fixed": FixedChunker,
    "recursive": RecursiveChunker,
    "markdown_header": MarkdownHeaderChunker,
}


def available_strategies() -> list[str]:
    return list(_STRATEGIES)


def get_chunker(strategy: str, **params) -> Chunker:
    """Build a chunker by strategy name, passing through only valid params.

    Unknown params are dropped rather than raising so the API can forward a
    single param bag regardless of which strategy the caller picked.
    """
    try:
        cls = _STRATEGIES[strategy]
    except KeyError:
        raise ValueError(
            f"unknown chunk strategy {strategy!r}; "
            f"choose from {available_strategies()}"
        ) from None
    valid = cls.__dataclass_fields__  # type: ignore[attr-defined]
    kwargs = {k: v for k, v in params.items() if k in valid and k != "name"}
    return cls(**kwargs)


def _validate_size_overlap(chunk_size: int, chunk_overlap: int) -> None:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be in [0, chunk_size)")


def _tail(text: str, n: int) -> str:
    """Last ``n`` characters of ``text`` (the overlap carried to the next chunk)."""
    return text[-n:] if n else ""
