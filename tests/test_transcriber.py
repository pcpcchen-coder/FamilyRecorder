from pathlib import Path

import pytest

from family_recorder.config import WhisperConfig
from family_recorder.transcriber import (
    TranscriptionError,
    WhisperCppTranscriber,
    correct_common_terms,
)


def _fake_whisper(tmp_path: Path, exit_code: int = 0) -> Path:
    script = tmp_path / "whisper-cli"
    script.write_text(
        f"""#!/usr/bin/env python3
import pathlib
import json
import sys

if {exit_code}:
    print("fake whisper failure", file=sys.stderr)
    raise SystemExit({exit_code})
base = pathlib.Path(sys.argv[sys.argv.index("-of") + 1])
base.with_suffix(".json").write_text(json.dumps({{
    "transcription": [
        {{"offsets": {{"from": 250, "to": 1750}}, "text": "  測試  逐字稿。 "}}
    ]
}}, ensure_ascii=False), encoding="utf-8")
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_whisper_cli_output_is_read_and_normalized(tmp_path: Path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    transcriber = WhisperCppTranscriber(
        WhisperConfig(binary_path=_fake_whisper(tmp_path), model_path=model)
    )
    assert transcriber.transcribe(audio) == "測試 逐字稿。"
    detailed = transcriber.transcribe_detailed(audio)
    assert detailed.segments[0].start_ms == 250
    assert detailed.segments[0].end_ms == 1750
    assert detailed.segments[0].text == "測試 逐字稿。"
    assert detailed.quality.compression_ratio is not None


def test_whisper_full_json_quality_is_calculated(tmp_path: Path) -> None:
    script = tmp_path / "whisper-cli"
    script.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys
base = pathlib.Path(sys.argv[sys.argv.index("-of") + 1])
base.with_suffix(".json").write_text(json.dumps({
    "transcription": [{
        "offsets": {"from": 0, "to": 1000},
        "text": "測試",
        "no_speech_prob": 0.2,
        "tokens": [
            {"text": "[_BEG_]", "p": 0.01},
            {"text": "測", "p": 0.9},
            {"text": "試", "p": 0.1}
        ]
    }]
}, ensure_ascii=False), encoding="utf-8")
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")

    result = WhisperCppTranscriber(
        WhisperConfig(binary_path=script, model_path=model)
    ).transcribe_detailed(audio)

    assert result.quality.token_count == 2
    assert result.quality.avg_logprob == pytest.approx(-1.2039728)
    assert result.quality.no_speech_probability == pytest.approx(0.2)
    assert result.quality.low_probability_ratio == pytest.approx(0.5)


def test_whisper_cli_error_is_actionable(tmp_path: Path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    transcriber = WhisperCppTranscriber(
        WhisperConfig(binary_path=_fake_whisper(tmp_path, 9), model_path=model)
    )
    with pytest.raises(TranscriptionError, match="fake whisper failure"):
        transcriber.transcribe(audio)


def test_common_term_correction_is_conservative() -> None:
    assert correct_common_terms("今天陳樂榮回家了", ("陳樂融",)) == "今天陳樂融回家了"
    assert correct_common_terms("今天陳月容回家了", ("陳樂融",)) == "今天陳月容回家了"
    assert correct_common_terms("陳樂容", ("陳樂融", "陳樂榮")) == "陳樂容"
    assert correct_common_terms("小陳來了", ("小王",)) == "小陳來了"
