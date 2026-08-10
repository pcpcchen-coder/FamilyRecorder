from pathlib import Path

from family_recorder.config_editor import update_yaml_scalar, update_yaml_value


def test_update_yaml_scalar_preserves_comments_and_other_settings(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """# keep this comment
whisper:
  model_path: "~/old.bin" # replaced as a whole scalar
  language: "zh"

summary:
  model: ""
  hour: 0
""",
        encoding="utf-8",
    )
    update_yaml_scalar(path, "whisper", "model_path", "/tmp/模型.bin")
    update_yaml_scalar(path, "summary", "model", "gpt-custom")

    updated = path.read_text(encoding="utf-8")
    assert "# keep this comment" in updated
    assert 'model_path: "/tmp/模型.bin"' in updated
    assert 'model: "gpt-custom"' in updated
    assert 'language: "zh"' in updated
    assert "hour: 0" in updated


def test_update_yaml_value_adds_new_section_and_values(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("audio:\n  chunk_seconds: 30\n", encoding="utf-8")

    update_yaml_value(path, "speakers", "members", ["我", "家人"])
    update_yaml_value(path, "speakers", "enabled", True)

    updated = path.read_text(encoding="utf-8")
    assert 'members: ["我", "家人"]' in updated
    assert "enabled: true" in updated
    assert "chunk_seconds: 30" in updated


def test_update_yaml_value_replaces_block_scalar_without_leaving_old_lines(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "summary:\n  prompt: |\n    舊的第一行\n    舊的第二行\n  hour: 0\n",
        encoding="utf-8",
    )

    update_yaml_value(path, "summary", "prompt", "新的第一行\n新的第二行")

    updated = path.read_text(encoding="utf-8")
    assert "舊的第一行" not in updated
    assert "hour: 0" in updated
    assert 'prompt: "新的第一行\\n新的第二行"' in updated
