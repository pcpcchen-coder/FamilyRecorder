from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from family_recorder.config import SpeakerConfig
from family_recorder.speakers import (
    SpeakerProfileStore,
    create_profile,
    identify_speaker,
)


def _synthetic_voice(
    pitch: float,
    formants: tuple[tuple[float, float], ...],
    *,
    seconds: int,
    phase: float = 0.0,
) -> bytes:
    sample_rate = 16_000
    times = np.arange(sample_rate * seconds) / sample_rate
    signal = np.zeros_like(times)
    for harmonic in range(1, 31):
        frequency = pitch * harmonic
        if frequency >= 7_000:
            break
        gain = sum(np.exp(-0.5 * ((frequency - center) / width) ** 2) for center, width in formants)
        signal += gain * np.sin(2 * np.pi * frequency * times + phase * harmonic) / harmonic
    signal *= 0.55 + 0.45 * np.sin(2 * np.pi * 2.7 * times) ** 2
    signal /= np.max(np.abs(signal))
    return (signal * 12_000).astype(np.int16).tobytes()


def test_profile_store_keeps_features_without_enrollment_audio(tmp_path: Path) -> None:
    audio = _synthetic_voice(
        125,
        ((700, 150), (1_200, 220), (2_500, 300)),
        seconds=12,
    )
    profile = create_profile("家人一", audio, 16_000)
    store = SpeakerProfileStore(tmp_path)
    path = store.save(profile)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["name"] == "家人一"
    assert len(payload["vectors"]) >= 3
    assert list(store.directory.glob("*.wav")) == []
    assert store.load("家人一") == profile


def test_identification_labels_known_voice_and_rejects_unknown() -> None:
    first_formants = ((700, 150), (1_200, 220), (2_500, 300))
    second_formants = ((450, 120), (1_800, 250), (3_000, 350))
    first = create_profile("家人一", _synthetic_voice(125, first_formants, seconds=15), 16_000)
    second = create_profile("家人二", _synthetic_voice(215, second_formants, seconds=15), 16_000)
    config = SpeakerConfig(enabled=True, members=("家人一", "家人二"))

    known = identify_speaker(
        _synthetic_voice(128, first_formants, seconds=9, phase=0.2),
        16_000,
        [first, second],
        config,
    )
    unknown = identify_speaker(
        _synthetic_voice(
            165,
            ((550, 120), (1_450, 250), (2_800, 350)),
            seconds=9,
            phase=0.7,
        ),
        16_000,
        [first, second],
        config,
    )

    assert known.label == "家人一"
    assert known.status == "recognized"
    assert known.confidence is not None and known.confidence > 0.9
    assert unknown.label is None
    assert unknown.status == "uncertain"
