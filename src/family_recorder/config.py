from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, TypeVar

import yaml


@dataclass(frozen=True)
class AudioConfig:
    device_name_contains: str = "XVF3800"
    device_id: int | None = None
    allow_default_input: bool = False
    sample_rate: int = 16_000
    channels: int = 1
    chunk_seconds: int = 30
    retry_seconds: int = 10


@dataclass(frozen=True)
class VadConfig:
    enabled: bool = True
    aggressiveness: int = 2
    frame_ms: int = 30
    min_speech_ratio: float = 0.08
    min_rms_dbfs: float = -48.0


@dataclass(frozen=True)
class WhisperConfig:
    binary_path: Path = Path(
        "~/Library/Application Support/FamilyRecorder/whisper.cpp/build/bin/whisper-cli"
    )
    model_path: Path = Path(
        "~/Library/Application Support/FamilyRecorder/whisper.cpp/models/ggml-large-v3-turbo.bin"
    )
    language: str = "zh"
    threads: int = 8
    initial_prompt: str = ""
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class StorageConfig:
    data_dir: Path = Path("~/xvf3800-listener-data")
    keep_audio_days: int = 7
    delete_audio_after_transcription: bool = False


@dataclass(frozen=True)
class SpeakerConfig:
    enabled: bool = False
    members: tuple[str, ...] = ()
    min_similarity: float = 0.82
    min_margin: float = 0.025
    dominance_threshold: float = 0.65


DEFAULT_SUMMARY_PROMPT = """\
你是家庭聲音日誌整理助手。只根據逐字稿內容整理，不得補造事件。
輸出繁體中文 Markdown，列出事件時間軸、重要消息、決策、待辦、想法、
關鍵實體、需要人工確認的片段，以及 100 字內摘要。各項保留來源段落的
約略時間；無法對應時明確標示時間不明。
"""


@dataclass(frozen=True)
class SummaryConfig:
    enabled: bool = True
    provider: str = "codex"
    model: str = ""
    codex_binary_path: str = "codex"
    timeout_seconds: int = 900
    hour: int = 0
    minute: int = 10
    max_input_chars: int = 300_000
    prompt: str = DEFAULT_SUMMARY_PROMPT


@dataclass(frozen=True)
class PlacementTestConfig:
    recording_seconds_per_sentence: int = 8
    sentences_file: Path | None = None


@dataclass(frozen=True)
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    speakers: SpeakerConfig = field(default_factory=SpeakerConfig)
    summary: SummaryConfig = field(default_factory=SummaryConfig)
    placement_test: PlacementTestConfig = field(default_factory=PlacementTestConfig)


T = TypeVar("T")


def _known_values(cls: type[T], values: dict[str, Any]) -> dict[str, Any]:
    allowed = {item.name for item in fields(cls)}
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"Unknown {cls.__name__} keys: {', '.join(unknown)}")
    return values


def _path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def load_config(path: str | Path) -> AppConfig:
    config_path = _path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a YAML mapping")

    allowed_sections = {item.name for item in fields(AppConfig)}
    unknown_sections = sorted(set(raw) - allowed_sections)
    if unknown_sections:
        raise ValueError(f"Unknown config sections: {', '.join(unknown_sections)}")

    audio = AudioConfig(**_known_values(AudioConfig, raw.get("audio", {})))
    vad = VadConfig(**_known_values(VadConfig, raw.get("vad", {})))

    whisper_values = _known_values(WhisperConfig, raw.get("whisper", {}))
    whisper_defaults = WhisperConfig()
    whisper_values["binary_path"] = _path(
        whisper_values.get("binary_path", whisper_defaults.binary_path)
    )
    whisper_values["model_path"] = _path(
        whisper_values.get("model_path", whisper_defaults.model_path)
    )
    if "extra_args" in whisper_values:
        whisper_values["extra_args"] = tuple(str(v) for v in whisper_values["extra_args"])
    whisper = WhisperConfig(**whisper_values)

    storage_values = _known_values(StorageConfig, raw.get("storage", {}))
    storage_values["data_dir"] = _path(storage_values.get("data_dir", StorageConfig().data_dir))
    storage = StorageConfig(**storage_values)

    speaker_values = _known_values(SpeakerConfig, raw.get("speakers", {}))
    if "members" in speaker_values:
        members = speaker_values["members"]
        if not isinstance(members, list):
            raise ValueError("speakers.members must be a YAML list")
        speaker_values["members"] = tuple(str(value).strip() for value in members)
    speakers = SpeakerConfig(**speaker_values)

    summary = SummaryConfig(**_known_values(SummaryConfig, raw.get("summary", {})))

    placement_values = _known_values(PlacementTestConfig, raw.get("placement_test", {}))
    sentences_file = placement_values.get("sentences_file")
    if sentences_file:
        placement_values["sentences_file"] = _path(sentences_file)
    elif "sentences_file" in placement_values:
        placement_values["sentences_file"] = None
    placement = PlacementTestConfig(**placement_values)

    config = AppConfig(
        audio=audio,
        vad=vad,
        whisper=whisper,
        storage=storage,
        speakers=speakers,
        summary=summary,
        placement_test=placement,
    )
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    if config.audio.sample_rate not in {8_000, 16_000, 32_000, 48_000}:
        raise ValueError("audio.sample_rate must be 8000, 16000, 32000, or 48000")
    if config.audio.channels < 1:
        raise ValueError("audio.channels must be at least 1")
    if config.audio.chunk_seconds < 1:
        raise ValueError("audio.chunk_seconds must be at least 1")
    if config.vad.aggressiveness not in range(4):
        raise ValueError("vad.aggressiveness must be 0, 1, 2, or 3")
    if config.vad.frame_ms not in {10, 20, 30}:
        raise ValueError("vad.frame_ms must be 10, 20, or 30")
    if not 0 <= config.vad.min_speech_ratio <= 1:
        raise ValueError("vad.min_speech_ratio must be between 0 and 1")
    if config.storage.keep_audio_days < 0:
        raise ValueError("storage.keep_audio_days cannot be negative")
    if len(config.speakers.members) > 8:
        raise ValueError("speakers.members supports at most 8 household members")
    if any(not name or len(name) > 80 for name in config.speakers.members):
        raise ValueError("speaker member names must contain 1 to 80 characters")
    normalized_names = [name.casefold() for name in config.speakers.members]
    if len(normalized_names) != len(set(normalized_names)):
        raise ValueError("speakers.members cannot contain duplicate names")
    if not 0 <= config.speakers.min_similarity <= 1:
        raise ValueError("speakers.min_similarity must be between 0 and 1")
    if not 0 <= config.speakers.min_margin <= 1:
        raise ValueError("speakers.min_margin must be between 0 and 1")
    if not 0.5 <= config.speakers.dominance_threshold <= 1:
        raise ValueError("speakers.dominance_threshold must be between 0.5 and 1")
    if not 0 <= config.summary.hour <= 23 or not 0 <= config.summary.minute <= 59:
        raise ValueError("summary.hour/minute is not a valid time")
    if config.summary.max_input_chars < 1_000:
        raise ValueError("summary.max_input_chars must be at least 1000")
    if config.summary.provider != "codex":
        raise ValueError("summary.provider must be 'codex'")
    if config.summary.timeout_seconds < 30:
        raise ValueError("summary.timeout_seconds must be at least 30")
