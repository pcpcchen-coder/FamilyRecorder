from pathlib import Path

from family_recorder.config_editor import update_yaml_scalar


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
