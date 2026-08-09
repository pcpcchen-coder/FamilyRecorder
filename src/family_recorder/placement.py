from __future__ import annotations

import re
import statistics
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from family_recorder.audio import AudioRecorder, write_wav
from family_recorder.config import AppConfig
from family_recorder.metrics import AudioAnalysis, analyze_audio
from family_recorder.transcriber import WhisperCppTranscriber

DEFAULT_SENTENCES = (
    "今天晚餐想吃番茄炒蛋和青菜。",
    "明天早上八點記得去拿包裹。",
    "客廳的窗戶晚上要記得關起來。",
    "請把牛奶、雞蛋和麵包加到購物清單。",
    "週末我們一起整理儲藏室。",
    "下午三點要跟供應商確認交期。",
    "這個麥克風需要離桌面大約十公分。",
    "背景有電視聲音時也要測試辨識率。",
    "Mac mini 會在本地執行 Whisper。",
    "XVF3800 透過 USB 傳送音訊。",
    "今天討論的決定請放進每日摘要。",
    "如果下雨就把陽台的衣服收進來。",
    "George 明天下午要去郵局寄文件。",
    "這段話包含中文、English 和數字二零二六。",
    "請不要把原始錄音上傳到雲端。",
    "七天後系統會清理舊的音訊檔案。",
    "我們需要比較桌面中央和櫃子上方。",
    "說話距離分別測試一公尺和三公尺。",
    "辨識錯誤的內容需要人工再次確認。",
    "完成測試後請選擇訊噪比最高的位置。",
)


@dataclass(frozen=True)
class PlacementResult:
    position: str
    sentence_number: int
    reference: str
    transcript: str
    audio_path: Path
    analysis: AudioAnalysis
    character_error_rate: float
    error: str | None = None


def normalize_for_comparison(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(
        character
        for character in normalized
        if not unicodedata.category(character).startswith(("P", "S", "Z", "C"))
    )


def character_error_rate(reference: str, hypothesis: str) -> float:
    left = normalize_for_comparison(reference)
    right = normalize_for_comparison(hypothesis)
    if not left:
        return 0.0 if not right else 1.0
    previous = list(range(len(right) + 1))
    for row, left_character in enumerate(left, start=1):
        current = [row]
        for column, right_character in enumerate(right, start=1):
            substitution = previous[column - 1] + (left_character != right_character)
            current.append(min(current[-1] + 1, previous[column] + 1, substitution))
        previous = current
    return previous[-1] / len(left)


def load_sentences(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return DEFAULT_SENTENCES
    sentences = tuple(
        line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    if not sentences:
        raise ValueError(f"Sentence file is empty: {path}")
    return sentences


def _safe_position_name(position: str) -> str:
    safe = re.sub(r"[^\w.-]+", "-", position.strip(), flags=re.UNICODE).strip("-.")
    return safe or "position"


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return statistics.fmean(values) if values else None


def render_report(results: list[PlacementResult], started_at: datetime) -> str:
    positions = list(dict.fromkeys(result.position for result in results))
    lines = [
        f"# Mic placement test — {started_at.isoformat(timespec='seconds')}",
        "",
        "較高 SNR、較高音量（較接近 0 dBFS）與較低 CER 通常代表更好的擺位。",
        "",
        "| 位置 | 成功/總數 | 平均 RMS dBFS | 平均 SNR dB | 平均 CER |",
        "|---|---:|---:|---:|---:|",
    ]
    for position in positions:
        rows = [result for result in results if result.position == position]
        success = [result for result in rows if result.error is None]
        rms = _mean(result.analysis.rms_dbfs for result in rows)
        snr = _mean(result.analysis.snr_db for result in rows if result.analysis.snr_db is not None)
        cer = _mean(result.character_error_rate for result in success)
        snr_text = "n/a" if snr is None else f"{snr:.1f}"
        cer_text = "n/a" if cer is None else f"{cer:.1%}"
        lines.append(
            f"| {position} | {len(success)}/{len(rows)} | {rms:.1f} | {snr_text} | {cer_text} |"
        )

    lines.extend(["", "## 每句結果", ""])
    for result in results:
        lines.extend(
            [
                f"### {result.position} · {result.sentence_number:02d}",
                "",
                f"- 固定句：{result.reference}",
                f"- 辨識：{result.transcript or '(空白)'}",
                f"- RMS：{result.analysis.rms_dbfs:.1f} dBFS",
                f"- SNR：{result.analysis.snr_db:.1f} dB"
                if result.analysis.snr_db is not None
                else "- SNR：n/a",
                f"- Speech ratio：{result.analysis.speech_ratio:.1%}",
                f"- CER：{result.character_error_rate:.1%}",
                f"- 音訊：`{result.audio_path}`",
            ]
        )
        if result.error:
            lines.append(f"- 錯誤：{result.error}")
        lines.append("")
    return "\n".join(lines)


def run_placement_test(
    config: AppConfig,
    positions: list[str],
    seconds: int | None = None,
    sentence_path: Path | None = None,
    prompt: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
) -> Path:
    seconds = seconds or config.placement_test.recording_seconds_per_sentence
    sentence_path = sentence_path or config.placement_test.sentences_file
    sentences = load_sentences(sentence_path)
    recorder = AudioRecorder(config.audio)
    transcriber = WhisperCppTranscriber(config.whisper)
    transcriber.validate()
    started_at = datetime.now().astimezone()
    root = config.storage.data_dir / "placement-tests" / started_at.strftime("%Y%m%d-%H%M%S")
    root.mkdir(parents=True, exist_ok=True)
    results: list[PlacementResult] = []

    for position_index, position in enumerate(positions, start=1):
        position_slug = f"{position_index:02d}-{_safe_position_name(position)}"
        output(f"\n請將麥克風移到位置 {position}，固定後按 Enter。")
        prompt("")
        with recorder.open_stream() as stream:
            output(f"使用音訊裝置：{recorder.device.name if recorder.device else 'unknown'}")
            for number, sentence in enumerate(sentences, start=1):
                prompt(f"\n[{position} {number}/{len(sentences)}] 按 Enter 後朗讀：\n{sentence}\n")
                chunk = recorder.read_chunk(stream, seconds)
                analysis = analyze_audio(chunk.pcm16_mono, chunk.sample_rate, config.vad)
                audio_path = root / position_slug / f"{number:02d}.wav"
                write_wav(audio_path, chunk.pcm16_mono, chunk.sample_rate)
                transcript = ""
                error: str | None = None
                try:
                    transcript = transcriber.transcribe(audio_path)
                except Exception as exc:
                    error = str(exc)
                result = PlacementResult(
                    position,
                    number,
                    sentence,
                    transcript,
                    audio_path,
                    analysis,
                    character_error_rate(sentence, transcript),
                    error,
                )
                results.append(result)
                output(
                    f"辨識：{transcript or '(空白)'} | RMS {analysis.rms_dbfs:.1f} dBFS | "
                    f"CER {result.character_error_rate:.1%}"
                )

    report_path = root / "report.md"
    report_path.write_text(render_report(results, started_at), encoding="utf-8")
    return report_path
