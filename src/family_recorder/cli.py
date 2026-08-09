from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import date
from pathlib import Path

from family_recorder.config import AppConfig, load_config
from family_recorder.config_editor import update_yaml_scalar
from family_recorder.control import pause_recording, read_pause_state, resume_recording
from family_recorder.devices import format_devices, list_input_devices, select_input_device
from family_recorder.listener import run_listener, validate_runtime_paths
from family_recorder.placement import run_placement_test
from family_recorder.storage import Storage
from family_recorder.summary import (
    DailySummaryRunner,
    SummaryError,
    check_codex_login,
    resolve_codex_binary,
)

DEFAULT_CONFIG = Path("~/.config/familyrecorder/config.yaml").expanduser()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="family-recorder",
        description="XVF3800 local listener and transcript journal for macOS",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list-devices", help="List macOS audio input devices")

    listen = commands.add_parser("listen", help="Run the continuous listener")
    listen.add_argument("--once", action="store_true", help="Process one chunk, then exit")

    summary = commands.add_parser("summary", help="Summarize a transcript using text only")
    summary.add_argument("--date", type=date.fromisoformat, dest="target_date")

    pause = commands.add_parser("pause", help="Temporarily pause microphone capture")
    pause.add_argument("--minutes", type=int, help="Automatically resume after this duration")
    commands.add_parser("resume", help="Resume microphone capture")

    whisper_model = commands.add_parser(
        "set-whisper-model", help="Select an already-downloaded whisper.cpp model"
    )
    whisper_model.add_argument("--path", type=Path, required=True)
    summary_model = commands.add_parser(
        "set-summary-model", help="Select a Codex summary model; empty uses the account default"
    )
    summary_model.add_argument("--model", required=True)
    commands.add_parser("menu-status", help=argparse.SUPPRESS)

    placement = commands.add_parser("placement-test", help="Compare microphone positions")
    placement.add_argument("--positions", nargs="+", default=["A", "B", "C"])
    placement.add_argument("--seconds", type=int)
    placement.add_argument("--sentences-file", type=Path)

    commands.add_parser("cleanup", help="Apply configured raw-audio retention now")
    commands.add_parser("doctor", help="Check configuration and runtime dependencies")
    return parser


def _load(path: Path) -> AppConfig:
    return load_config(path)


def _doctor(config: AppConfig) -> int:
    failed = False
    architecture = platform.machine()
    print(f"[{'OK' if architecture == 'arm64' else 'WARN'}] architecture: {architecture}")
    for label, path, exists in validate_runtime_paths(config):
        print(f"[{'OK' if exists else 'MISSING'}] {label}: {path}")
        failed = failed or (not exists and label != "data directory")
    try:
        device = select_input_device(config.audio)
        print(f"[OK] selected input: [{device.index}] {device.name}")
    except Exception as exc:
        print(f"[MISSING] audio input: {exc}")
        failed = True
    if config.summary.enabled:
        try:
            binary = resolve_codex_binary(config.summary.codex_binary_path)
            status = check_codex_login(config.summary, binary=binary)
            print(f"[OK] Codex binary: {binary}")
            print(f"[OK] ChatGPT login: {status}")
        except SummaryError as exc:
            print(f"[MISSING] ChatGPT login: {exc}")
            failed = True
    return int(failed)


def _listener_is_running() -> bool:
    result = subprocess.run(
        [
            "/bin/launchctl",
            "print",
            f"gui/{os.getuid()}/com.familyrecorder.listener",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and "state = running" in result.stdout


def _model_name(path: Path) -> str:
    name = path.stem
    return name.removeprefix("ggml-")


def _menu_status(config: AppConfig, config_path: Path) -> dict[str, object]:
    pause_state = read_pause_state(config.storage.data_dir)
    model_paths = sorted(config.whisper.model_path.parent.glob("ggml-*.bin"))
    today = date.today()
    data_dir = config.storage.data_dir
    return {
        "paused": pause_state.paused,
        "pause_label": pause_state.label,
        "pause_until": pause_state.until.isoformat() if pause_state.until else None,
        "listener_running": _listener_is_running(),
        "config_path": str(config_path.expanduser().resolve()),
        "data_dir": str(data_dir),
        "transcript_dir": str(data_dir / "transcripts"),
        "summary_dir": str(data_dir / "summaries"),
        "audio_dir": str(data_dir / "audio"),
        "log_dir": str(data_dir / "logs"),
        "today_transcript": str(data_dir / "transcripts" / f"{today.isoformat()}.md"),
        "today_summary": str(data_dir / "summaries" / f"{today.isoformat()}.md"),
        "current_whisper_model": _model_name(config.whisper.model_path),
        "current_whisper_model_path": str(config.whisper.model_path),
        "whisper_models": [
            {"name": _model_name(path), "path": str(path.resolve())} for path in model_paths
        ],
        "summary_model": config.summary.model,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        if args.command == "list-devices":
            print(format_devices(list_input_devices()))
            return 0

        config = _load(args.config)
        if args.command == "listen":
            run_listener(config, once=args.once)
            return 0
        if args.command == "summary":
            path = DailySummaryRunner(config).run(args.target_date)
            print(path)
            return 0
        if args.command == "pause":
            state = pause_recording(config.storage.data_dir, minutes=args.minutes)
            print(state.label)
            return 0
        if args.command == "resume":
            state = resume_recording(config.storage.data_dir)
            print(state.label)
            return 0
        if args.command == "set-whisper-model":
            model_path = args.path.expanduser().resolve()
            if not model_path.is_file():
                raise FileNotFoundError(f"Whisper model not found: {model_path}")
            update_yaml_scalar(
                args.config.expanduser().resolve(), "whisper", "model_path", str(model_path)
            )
            print(f"Whisper model: {_model_name(model_path)}")
            return 0
        if args.command == "set-summary-model":
            update_yaml_scalar(
                args.config.expanduser().resolve(), "summary", "model", args.model.strip()
            )
            print(f"Summary model: {args.model.strip() or 'ChatGPT account default'}")
            return 0
        if args.command == "menu-status":
            print(json.dumps(_menu_status(config, args.config), ensure_ascii=False))
            return 0
        if args.command == "placement-test":
            if args.seconds is not None and args.seconds < 1:
                raise ValueError("--seconds must be at least 1")
            path = run_placement_test(
                config,
                positions=args.positions,
                seconds=args.seconds,
                sentence_path=args.sentences_file,
            )
            print(f"Placement report: {path}")
            return 0
        if args.command == "cleanup":
            with Storage(config.storage) as storage:
                result = storage.cleanup_audio()
            print(f"Removed {result.removed_files} files ({result.removed_bytes} bytes)")
            return 0
        if args.command == "doctor":
            return _doctor(config)
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        logging.getLogger(__name__).error("%s", exc)
        if args.verbose:
            logging.getLogger(__name__).exception("Command failed")
        return 1
    return 2
