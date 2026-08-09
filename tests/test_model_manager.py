from pathlib import Path
from types import SimpleNamespace

import pytest

from family_recorder.config import AppConfig, WhisperConfig
from family_recorder.model_manager import (
    MODEL_BASE_URL,
    ModelDownloadError,
    download_whisper_model,
    downloadable_models,
)


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(whisper=WhisperConfig(model_path=tmp_path / "ggml-current.bin"))


def test_download_model_uses_allowlisted_official_url_and_atomic_partial(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("family_recorder.model_manager.MIN_MODEL_BYTES", 4)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        partial = Path(command[command.index("--output") + 1])
        partial.write_bytes(b"lmgg-valid-model")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    target, downloaded = download_whisper_model(_config(tmp_path), "tiny", command_runner=runner)

    assert downloaded is True
    assert target == (tmp_path / "ggml-tiny.bin").resolve()
    assert target.read_bytes() == b"lmgg-valid-model"
    assert not (tmp_path / ".ggml-tiny.bin.partial").exists()
    command, kwargs = calls[0]
    assert command[-1] == f"{MODEL_BASE_URL}/ggml-tiny.bin"
    assert "--fail" in command
    assert "--continue-at" in command
    assert kwargs["check"] is False


def test_download_model_reuses_an_existing_valid_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("family_recorder.model_manager.MIN_MODEL_BYTES", 4)
    target = tmp_path / "ggml-small.bin"
    target.write_bytes(b"lmgg-valid-model")

    def should_not_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        raise AssertionError("curl should not run for an installed model")

    result, downloaded = download_whisper_model(
        _config(tmp_path), "small", command_runner=should_not_run
    )

    assert result == target.resolve()
    assert downloaded is False


def test_download_model_rejects_unknown_name(tmp_path: Path) -> None:
    with pytest.raises(ModelDownloadError, match="不支援"):
        download_whisper_model(_config(tmp_path), "../../not-a-model")


def test_download_model_does_not_select_an_invalid_response(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("family_recorder.model_manager.MIN_MODEL_BYTES", 4)

    def runner(command: list[str], **_kwargs: object) -> SimpleNamespace:
        partial = Path(command[command.index("--output") + 1])
        partial.write_bytes(b"html-error-page")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with pytest.raises(ModelDownloadError, match="格式驗證失敗"):
        download_whisper_model(_config(tmp_path), "base", command_runner=runner)

    assert not (tmp_path / "ggml-base.bin").exists()
    assert not (tmp_path / ".ggml-base.bin.partial").exists()


def test_downloadable_models_marks_installed_and_excludes_english_only(tmp_path: Path) -> None:
    (tmp_path / "ggml-medium.bin").write_bytes(b"installed")

    models = downloadable_models(_config(tmp_path))
    names = {str(model["name"]) for model in models}
    medium = next(model for model in models if model["name"] == "medium")

    assert "medium" in names
    assert "medium.en" not in names
    assert medium["installed"] is True
