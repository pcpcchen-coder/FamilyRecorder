from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from family_recorder.config import AppConfig
from family_recorder.keychain import read_generic_password
from family_recorder.storage import Storage


class SummaryError(RuntimeError):
    """Raised when a daily summary cannot be generated."""


def previous_local_date(now: datetime | None = None) -> date:
    now = now or datetime.now().astimezone()
    return (now - timedelta(days=1)).date()


def split_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for line in text.splitlines(keepends=True):
        if len(line) > max_chars:
            if current:
                chunks.append("".join(current))
                current, current_size = [], 0
            chunks.extend(
                line[offset : offset + max_chars] for offset in range(0, len(line), max_chars)
            )
            continue
        if current and current_size + len(line) > max_chars:
            chunks.append("".join(current))
            current, current_size = [], 0
        current.append(line)
        current_size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def _default_client_factory(api_key: str) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=api_key)


class DailySummaryRunner:
    def __init__(
        self,
        config: AppConfig,
        client_factory: Callable[[str], Any] = _default_client_factory,
        key_reader: Callable[[str, str | None], str] = read_generic_password,
    ) -> None:
        self.config = config
        self.client_factory = client_factory
        self.key_reader = key_reader

    def _request(self, client: Any, instructions: str, content: str) -> str:
        response = client.responses.create(
            model=self.config.summary.model,
            instructions=instructions,
            input=content,
            store=False,
        )
        raw_output = response.output_text
        if not isinstance(raw_output, str) or not raw_output.strip():
            raise SummaryError("Cloud AI returned an empty summary")
        return raw_output.strip()

    def run(self, target_date: date | None = None) -> Path:
        if not self.config.summary.enabled:
            raise SummaryError("Daily summaries are disabled in config")
        if self.config.summary.provider != "openai":
            raise SummaryError(
                f"Unsupported summary provider: {self.config.summary.provider!r}; expected 'openai'"
            )

        target_date = target_date or previous_local_date()
        with Storage(self.config.storage) as storage:
            transcript_path = storage.transcript_path_for(target_date)
            if not transcript_path.is_file():
                raise SummaryError(f"No transcript exists for {target_date.isoformat()}")
            transcript = transcript_path.read_text(encoding="utf-8").strip()
            if not transcript:
                raise SummaryError(f"Transcript for {target_date.isoformat()} is empty")

            api_key = self.key_reader(
                self.config.summary.keychain_service,
                self.config.summary.keychain_account,
            )
            client = self.client_factory(api_key)
            parts = split_text(transcript, self.config.summary.max_input_chars)
            if len(parts) == 1:
                summary = self._request(
                    client,
                    self.config.summary.prompt,
                    f"日期：{target_date.isoformat()}\n\n逐字稿：\n{parts[0]}",
                )
            else:
                partials = [
                    self._request(
                        client,
                        self.config.summary.prompt
                        + "\n這是分段逐字稿。先整理這一段，保留不確定性，不要補造。",
                        f"日期：{target_date.isoformat()}；第 {index}/{len(parts)} 段\n\n{part}",
                    )
                    for index, part in enumerate(parts, start=1)
                ]
                summary = self._request(
                    client,
                    self.config.summary.prompt
                    + "\n以下是同一天各段的中間整理，請去重並整合成一份最終摘要。",
                    "\n\n--- 分段整理 ---\n\n".join(partials),
                )

            summary_path = storage.summary_path_for(target_date)
            summary_path.write_text(
                f"# FamilyRecorder daily summary — {target_date.isoformat()}\n\n{summary}\n",
                encoding="utf-8",
            )
            storage.record_summary(target_date, summary_path, self.config.summary.model)
            return summary_path
