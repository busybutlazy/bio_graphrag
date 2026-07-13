import pytest

from ingestion.extract import parse_document as pd


def test_parse_full_front_matter(tmp_path):
    src = tmp_path / "thyroid.md"
    src.write_text(
        "---\n"
        "doc_id: doc:endocrine:thyroid\n"
        "title: 甲狀腺與代謝調節\n"
        "topic: thyroid_regulation\n"
        "grade_level: 高二\n"
        "source_type: textbook\n"
        "extraction_profile: endocrine\n"
        "---\n"
        "# 甲狀腺\n正文內容。",
        encoding="utf-8",
    )
    doc = pd.parse_document(src)
    assert doc.doc_id == "doc:endocrine:thyroid"
    assert doc.title == "甲狀腺與代謝調節"
    assert doc.topic == "thyroid_regulation"
    assert doc.grade_level == "高二"
    assert doc.source_type == "textbook"
    assert doc.extraction_profile == "endocrine"
    assert doc.body.startswith("# 甲狀腺")


def test_document_row_shape_matches_loader():
    doc = pd.ParsedDocument(
        doc_id="doc:x",
        title="X",
        body="b",
        topic="t",
        grade_level="高二",
        source_type="sample",
    )
    row = doc.document_row()
    assert set(row) == {"doc_id", "title", "topic", "grade_level", "source_type"}


def test_missing_front_matter_treats_all_as_body(tmp_path):
    src = tmp_path / "plain.md"
    src.write_text("沒有 front-matter 的純內容。", encoding="utf-8")
    doc = pd.parse_document(src)
    assert doc.doc_id == "doc:plain"
    assert doc.body == "沒有 front-matter 的純內容。"
    assert doc.extraction_profile is None


def test_quotes_stripped_from_values(tmp_path):
    src = tmp_path / "q.md"
    src.write_text('---\ntitle: "帶引號的標題"\n---\n內容', encoding="utf-8")
    doc = pd.parse_document(src)
    assert doc.title == "帶引號的標題"


def test_unclosed_front_matter_raises(tmp_path):
    src = tmp_path / "bad.md"
    src.write_text("---\ntitle: X\n沒有結束的 fence", encoding="utf-8")
    with pytest.raises(pd.DocumentParseError):
        pd.parse_document(src)


def test_empty_body_raises(tmp_path):
    src = tmp_path / "empty.md"
    src.write_text("---\ntitle: X\n---\n   ", encoding="utf-8")
    with pytest.raises(pd.DocumentParseError):
        pd.parse_document(src)


def test_missing_file_raises():
    with pytest.raises(pd.DocumentParseError):
        pd.parse_document("/nonexistent/path/foo.md")


def test_unknown_keys_ignored(tmp_path):
    src = tmp_path / "extra.md"
    src.write_text("---\ntitle: X\nauthor: 老師\n---\n內容", encoding="utf-8")
    doc = pd.parse_document(src)  # unknown front-matter key is silently dropped, no raise
    assert doc.title == "X"
    assert doc.body == "內容"
