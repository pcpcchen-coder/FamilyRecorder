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
    common_terms: tuple[str, ...] = ()
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


@dataclass(frozen=True)
class DirectionConfig:
    enabled: bool = True
    sample_interval_seconds: float = 0.25
    front_angle_degrees: float = 0.0
    min_speech_samples: int = 3
    cluster_tolerance_degrees: float = 35.0
    multiple_direction_min_ratio: float = 0.25
    speech_energy_enabled: bool = True
    speech_energy_min_ratio: float = 0.08
    speech_energy_min_rms_dbfs: float = -55.0
    speech_energy_threshold: float = 0.0
    usb_timeout_ms: int = 1_000


@dataclass(frozen=True)
class CalendarConfig:
    enabled: bool = False
    auto_create: bool = False
    provider: str = "google"
    default_calendar_id: str = ""
    default_calendar_name: str = ""
    calendar_names: dict[str, str] = field(default_factory=dict)
    member_calendar_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    member_default_calendar_ids: dict[str, str] = field(default_factory=dict)


DEFAULT_SUMMARY_PROMPT = """\
你是家庭聲音日誌整理助手。只根據逐字稿內容整理，不得補造事件。
輸出繁體中文 Markdown，列出事件時間軸、依可能說話者整理的家庭成員重點、
對話方向與人別線索、
重要消息、決策、待辦、想法、關鍵實體、需要人工確認的片段，以及 100 字內摘要。
各項保留來源段落的約略時間、可能說話者與收音方向；無法對應時明確標示不明。
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
    direction: DirectionConfig = field(default_factory=DirectionConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
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
    if "common_terms" in whisper_values:
        common_terms = whisper_values["common_terms"]
        if not isinstance(common_terms, list):
            raise ValueError("whisper.common_terms must be a YAML list")
        whisper_values["common_terms"] = tuple(str(v).strip() for v in common_terms)
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

    direction = DirectionConfig(**_known_values(DirectionConfig, raw.get("direction", {})))

    calendar_values = _known_values(CalendarConfig, raw.get("calendar", {}))
    if "member_calendar_ids" in calendar_values:
        mapping = calendar_values["member_calendar_ids"]
        if not isinstance(mapping, dict):
            raise ValueError("calendar.member_calendar_ids must be a YAML mapping")
        calendar_values["member_calendar_ids"] = {
            str(member): tuple(str(calendar_id) for calendar_id in calendar_ids)
            for member, calendar_ids in mapping.items()
            if isinstance(calendar_ids, list)
        }
        if len(calendar_values["member_calendar_ids"]) != len(mapping):
            raise ValueError("calendar.member_calendar_ids values must be YAML lists")
    if "calendar_names" in calendar_values:
        names = calendar_values["calendar_names"]
        if not isinstance(names, dict):
            raise ValueError("calendar.calendar_names must be a YAML mapping")
        calendar_values["calendar_names"] = {
            str(calendar_id): str(name) for calendar_id, name in names.items()
        }
    if "member_default_calendar_ids" in calendar_values:
        defaults = calendar_values["member_default_calendar_ids"]
        if not isinstance(defaults, dict):
            raise ValueError("calendar.member_default_calendar_ids must be a YAML mapping")
        calendar_values["member_default_calendar_ids"] = {
            str(member): str(calendar_id) for member, calendar_id in defaults.items()
        }
    calendar = CalendarConfig(**calendar_values)

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
        direction=direction,
        calendar=calendar,
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
    if len(config.whisper.common_terms) > 100:
        raise ValueError("whisper.common_terms supports at most 100 terms")
    if any(not term or len(term) > 40 for term in config.whisper.common_terms):
        raise ValueError("common terms must contain 1 to 40 characters")
    normalized_terms = [term.casefold() for term in config.whisper.common_terms]
    if len(normalized_terms) != len(set(normalized_terms)):
        raise ValueError("whisper.common_terms cannot contain duplicate terms")
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
    if not 0.1 <= config.direction.sample_interval_seconds <= 5:
        raise ValueError("direction.sample_interval_seconds must be between 0.1 and 5")
    if not 0 <= config.direction.front_angle_degrees < 360:
        raise ValueError("direction.front_angle_degrees must be between 0 and 360")
    if config.direction.min_speech_samples < 1:
        raise ValueError("direction.min_speech_samples must be at least 1")
    if not 5 <= config.direction.cluster_tolerance_degrees <= 90:
        raise ValueError("direction.cluster_tolerance_degrees must be between 5 and 90")
    if not 0.1 <= config.direction.multiple_direction_min_ratio <= 0.5:
        raise ValueError("direction.multiple_direction_min_ratio must be between 0.1 and 0.5")
    if not 0 <= config.direction.speech_energy_min_ratio <= 1:
        raise ValueError("direction.speech_energy_min_ratio must be between 0 and 1")
    if not -120 <= config.direction.speech_energy_min_rms_dbfs <= 0:
        raise ValueError("direction.speech_energy_min_rms_dbfs must be between -120 and 0")
    if config.direction.speech_energy_threshold < 0:
        raise ValueError("direction.speech_energy_threshold cannot be negative")
    if not 100 <= config.direction.usb_timeout_ms <= 10_000:
        raise ValueError("direction.usb_timeout_ms must be between 100 and 10000")
    if config.calendar.provider != "google":
        raise ValueError("calendar.provider must be 'google'")
    if any(
        not calendar_id or not name for calendar_id, name in config.calendar.calendar_names.items()
    ):
        raise ValueError("calendar names cannot contain empty values")
    for member, calendar_ids in config.calendar.member_calendar_ids.items():
        if not member or any(not calendar_id for calendar_id in calendar_ids):
            raise ValueError("calendar member mappings cannot contain empty values")
        if len(calendar_ids) != len(set(calendar_ids)):
            raise ValueError("calendar member mappings cannot contain duplicate calendar IDs")
    for member, calendar_id in config.calendar.member_default_calendar_ids.items():
        if calendar_id not in config.calendar.member_calendar_ids.get(member, ()):
            raise ValueError("each member default calendar must also be assigned to that member")
    if not 0 <= config.summary.hour <= 23 or not 0 <= config.summary.minute <= 59:
        raise ValueError("summary.hour/minute is not a valid time")
    if config.summary.max_input_chars < 1_000:
        raise ValueError("summary.max_input_chars must be at least 1000")
    if config.summary.provider != "codex":
        raise ValueError("summary.provider must be 'codex'")
    if config.summary.timeout_seconds < 30:
        raise ValueError("summary.timeout_seconds must be at least 30")
    if not config.summary.prompt.strip():
        raise ValueError("summary.prompt cannot be empty")
    if len(config.summary.prompt) > 20_000:
        raise ValueError("summary.prompt cannot exceed 20000 characters")
