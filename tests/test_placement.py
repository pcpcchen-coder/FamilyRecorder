from datetime import UTC, datetime
from pathlib import Path

from family_recorder.metrics import AudioAnalysis
from family_recorder.placement import (
    DEFAULT_SENTENCES,
    PlacementResult,
    character_error_rate,
    normalize_for_comparison,
    render_report,
)


def test_default_test_has_twenty_fixed_sentences() -> None:
    assert len(DEFAULT_SENTENCES) == 20
    assert len(set(DEFAULT_SENTENCES)) == 20


def test_character_error_rate_ignores_spacing_and_punctuation() -> None:
    assert normalize_for_comparison("Hello，世界！") == "hello世界"
    assert character_error_rate("明天記得拿包裹。", "明天 記得拿包裹") == 0
    assert character_error_rate("甲乙丙", "甲丁丙") == 1 / 3


def test_report_compares_positions() -> None:
    analysis = AudioAnalysis(True, -22.0, 15.0, 0.6, 10)
    results = [
        PlacementResult("A", 1, "測試", "測試", Path("A/01.wav"), analysis, 0.0),
        PlacementResult("B", 1, "測試", "測式", Path("B/01.wav"), analysis, 0.5),
    ]
    report = render_report(results, datetime(2026, 8, 9, tzinfo=UTC))
    assert "| A | 1/1 |" in report
    assert "| B | 1/1 |" in report
    assert "50.0%" in report
