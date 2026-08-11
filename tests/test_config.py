from pathlib import Path

import pytest

from family_recorder.config import load_config


def test_load_config_expands_paths_and_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
audio:
  device_name_contains: XMOS
storage:
  data_dir: ~/family-data
whisper:
  binary_path: ~/bin/whisper-cli
  model_path: ~/models/model.bin
""",
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.audio.device_name_contains == "XMOS"
    assert config.audio.chunk_seconds == 30
    assert config.direction.enabled is True
    assert config.direction.sample_interval_seconds == 0.25
    assert config.storage.data_dir == (tmp_path / "family-data").resolve()
    assert config.whisper.binary_path == (tmp_path / "bin/whisper-cli").resolve()


def test_load_config_accepts_common_terms(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        'whisper:\n  common_terms: ["陳樂融", "FamilyRecorder"]\n', encoding="utf-8"
    )
    config = load_config(config_file)
    assert config.whisper.common_terms == ("陳樂融", "FamilyRecorder")


def test_load_config_rejects_unknown_key(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("audio:\n  mystery: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown AudioConfig keys"):
        load_config(config_file)


def test_default_paths_are_expanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = tmp_path / "config.yaml"
    config_file.write_text("{}\n", encoding="utf-8")
    config = load_config(config_file)
    assert str(config.storage.data_dir).startswith(str(tmp_path))
    assert "~" not in str(config.whisper.binary_path)


def test_load_config_validates_vad_frame_size(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("vad:\n  frame_ms: 25\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frame_ms"):
        load_config(config_file)


def test_load_config_rejects_api_summary_provider(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("summary:\n  provider: openai\n", encoding="utf-8")
    with pytest.raises(ValueError, match="provider must be 'codex'"):
        load_config(config_file)


def test_load_config_accepts_household_members(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        'speakers:\n  enabled: true\n  members: ["我", "家人二", "家人三"]\n',
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.speakers.enabled is True
    assert config.speakers.members == ("我", "家人二", "家人三")


def test_load_config_rejects_duplicate_household_members(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        'speakers:\n  enabled: true\n  members: ["家人", "家人"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_config(config_file)


def test_load_config_accepts_direction_calibration(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "direction:\n  enabled: true\n  front_angle_degrees: 183.5\n",
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.direction.enabled is True
    assert config.direction.front_angle_degrees == 183.5


def test_load_config_accepts_google_calendar_member_mappings(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """calendar:
  enabled: true
  provider: google
  default_calendar_id: family-id
  default_calendar_name: Family
  calendar_names: {school-id: School, family-id: Family}
  member_calendar_ids:
    陳樂融: [school-id, family-id]
  member_default_calendar_ids:
    陳樂融: school-id
""",
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.calendar.provider == "google"
    assert config.calendar.member_calendar_ids["陳樂融"] == ("school-id", "family-id")
    assert config.calendar.calendar_names["school-id"] == "School"
    assert config.calendar.member_default_calendar_ids["陳樂融"] == "school-id"


def test_load_config_rejects_invalid_direction_interval(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("direction:\n  sample_interval_seconds: 0.01\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sample_interval_seconds"):
        load_config(config_file)
