from ingestion.pipeline import build_extraction_prompt as bep


def test_base_system_prompt_has_no_overlay_when_profile_missing():
    system = bep.build_system_prompt("does_not_exist")
    assert "章節特化補充" not in system
    assert "extraction agent" in system


def test_none_profile_returns_generic_system_prompt():
    assert bep.build_system_prompt(None) == bep.build_system_prompt("")


def test_profile_overlay_is_appended(tmp_path, monkeypatch):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "endocrine.profile.md").write_text(
        "優先 node type:Hormone, Receptor", encoding="utf-8"
    )
    monkeypatch.setattr(bep, "PROFILES_DIR", profile_dir)

    system = bep.build_system_prompt("endocrine")
    assert "章節特化補充(profile: endocrine)" in system
    assert "優先 node type:Hormone, Receptor" in system


def test_user_prompt_substitutes_placeholders():
    user = bep.build_user_prompt(
        chunk_id="chunk:1",
        existing_concepts="- c1: 胰島素",
        chunk_text="胰島素降低血糖。",
    )
    assert "chunk_id: chunk:1" in user
    assert "胰島素降低血糖。" in user
    assert "- c1: 胰島素" in user
