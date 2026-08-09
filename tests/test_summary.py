from datetime import date
from pathlib import Path
from types import SimpleNamespace

from family_recorder.config import AppConfig, StorageConfig, SummaryConfig
from family_recorder.summary import DailySummaryRunner, split_text


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(output_text="- 今日摘要：記得拿包裹。")


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_summary_uploads_transcript_text_with_store_false(tmp_path: Path) -> None:
    target = date(2026, 8, 9)
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir(parents=True)
    (transcript_dir / f"{target}.md").write_text("### 12:00\n記得拿包裹。\n", encoding="utf-8")
    audio_dir = tmp_path / "audio" / str(target)
    audio_dir.mkdir(parents=True)
    (audio_dir / "secret.wav").write_bytes(b"never upload this")

    config = AppConfig(
        storage=StorageConfig(data_dir=tmp_path),
        summary=SummaryConfig(model="gpt-test", max_input_chars=10_000),
    )
    client = FakeClient()
    key_calls: list[tuple[str, str | None]] = []

    def key_reader(service: str, account: str | None) -> str:
        key_calls.append((service, account))
        return "test-key"

    runner = DailySummaryRunner(config, client_factory=lambda _key: client, key_reader=key_reader)
    result = runner.run(target)

    assert result.read_text(encoding="utf-8").startswith("# FamilyRecorder daily summary")
    assert key_calls == [("familyrecorder-openai", None)]
    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["store"] is False
    assert call["model"] == "gpt-test"
    assert "記得拿包裹" in str(call["input"])
    assert "secret.wav" not in str(call)


def test_split_text_respects_limit() -> None:
    chunks = split_text("line one\nline two\nline three\n", 12)
    assert "".join(chunks) == "line one\nline two\nline three\n"
    assert all(len(chunk) <= 12 for chunk in chunks)
