import pytest

from ingestion.extract import chunkers


def test_available_strategies_lists_three():
    assert set(chunkers.available_strategies()) == {"fixed", "recursive", "markdown_header"}


def test_get_chunker_unknown_strategy_raises():
    with pytest.raises(ValueError):
        chunkers.get_chunker("nope")


def test_get_chunker_drops_irrelevant_params():
    # max_section_size belongs to markdown_header, not fixed; must be ignored.
    ch = chunkers.get_chunker("fixed", chunk_size=100, max_section_size=999)
    assert isinstance(ch, chunkers.FixedChunker)
    assert ch.chunk_size == 100


# --- fixed --------------------------------------------------------------------


def test_fixed_covers_all_text_with_overlap():
    text = "abcdefghij" * 10  # 100 chars, no whitespace to strip
    ch = chunkers.FixedChunker(chunk_size=30, chunk_overlap=10)
    parts = ch.chunk(text)
    assert parts, "expected at least one chunk"
    # dropping each chunk's leading overlap reconstructs the source exactly
    reconstructed = parts[0] + "".join(p[10:] for p in parts[1:])
    assert reconstructed == text
    assert all(len(p) <= 30 for p in parts)


def test_fixed_empty_text_returns_empty():
    assert chunkers.FixedChunker().chunk("   ") == []


def test_fixed_rejects_bad_overlap():
    with pytest.raises(ValueError):
        chunkers.FixedChunker(chunk_size=10, chunk_overlap=10)


# --- recursive ----------------------------------------------------------------


def test_recursive_respects_size_budget():
    text = "\n\n".join(f"段落{i}。" * 20 for i in range(5))
    ch = chunkers.RecursiveChunker(chunk_size=120, chunk_overlap=20)
    parts = ch.chunk(text)
    assert len(parts) > 1
    # allow a little slack for the carried overlap prefix
    assert all(len(p) <= 120 + 20 for p in parts)


def test_recursive_prefers_paragraph_boundaries():
    text = "第一段內容。\n\n第二段內容。\n\n第三段內容。"
    # The public API enforces chunk_size >= 100. This focused unit test uses a
    # tiny synthetic input, so disable the independent short-tail merge limit.
    ch = chunkers.RecursiveChunker(chunk_size=12, chunk_overlap=0, min_chunk_size=0)
    parts = ch.chunk(text)
    assert any("第一段" in p for p in parts)
    assert any("第三段" in p for p in parts)


def test_recursive_hard_splits_unbreakable_run():
    text = "x" * 250  # no separators at all
    ch = chunkers.RecursiveChunker(chunk_size=100, chunk_overlap=0)
    parts = ch.chunk(text)
    assert all(len(p) <= 100 for p in parts)
    assert "".join(parts) == text


# --- merge-back (min_chunk_size) ----------------------------------------------


def test_recursive_short_tail_merges_into_previous_chunk():
    # Two 50-char blocks + 5-char tail; tail is below min_chunk_size so it
    # must be appended to the previous chunk, not returned as a standalone piece.
    long1 = "A" * 50
    long2 = "B" * 50
    short_tail = "C" * 5
    text = long1 + " " + long2 + " " + short_tail
    ch = chunkers.RecursiveChunker(chunk_size=50, chunk_overlap=0, min_chunk_size=20)
    parts = ch.chunk(text)
    assert not any(p == short_tail for p in parts), "short tail must not be a standalone chunk"
    assert any(short_tail in p for p in parts), "short tail content must not be discarded"
    assert all(len(p) >= 20 for p in parts)


def test_recursive_only_chunk_below_min_is_kept():
    # When there is no previous chunk to merge into, a short piece must be
    # returned as-is rather than discarded.
    text = "x" * 5
    ch = chunkers.RecursiveChunker(chunk_size=50, chunk_overlap=0, min_chunk_size=20)
    parts = ch.chunk(text)
    assert parts == ["x" * 5]


def test_recursive_tail_exactly_at_min_size_is_standalone():
    # len(tail) == min_chunk_size must NOT trigger merge-back (condition is strict <).
    long1 = "A" * 50
    tail_at_boundary = "B" * 20  # exactly min_chunk_size
    text = long1 + " " + tail_at_boundary
    ch = chunkers.RecursiveChunker(chunk_size=50, chunk_overlap=0, min_chunk_size=20)
    parts = ch.chunk(text)
    assert parts[-1] == tail_at_boundary, "tail at min_chunk_size boundary must be its own chunk"


# --- markdown_header ----------------------------------------------------------


def test_markdown_header_splits_on_headers():
    text = "# 章 A\n內容一\n\n## 節 B\n內容二\n\n### 小節 C\n內容三"
    ch = chunkers.MarkdownHeaderChunker(max_section_size=1000)
    parts = ch.chunk(text)
    assert len(parts) == 3
    assert parts[0].startswith("# 章 A")
    assert parts[1].startswith("## 節 B")
    assert parts[2].startswith("### 小節 C")


def test_markdown_header_falls_back_for_long_section():
    long_body = "。".join(f"句子{i}" for i in range(200))
    text = f"# 巨大章節\n{long_body}"
    ch = chunkers.MarkdownHeaderChunker(max_section_size=150)
    parts = ch.chunk(text)
    assert len(parts) > 1
    assert all(len(p) <= 150 + 1 for p in parts)


def test_markdown_header_content_before_first_header_kept():
    text = "前言沒有標題。\n\n# 第一章\n正文"
    ch = chunkers.MarkdownHeaderChunker(max_section_size=1000)
    parts = ch.chunk(text)
    assert any("前言" in p for p in parts)
