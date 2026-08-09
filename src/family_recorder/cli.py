from __future__ import annotations

import argparse
import logging
import platform
import sys
from datetime import date
from pathlib import Path

from family_recorder.config import AppConfig, load_config
from family_recorder.devices import format_devices, list_input_devices, select_input_device
from family_recorder.keychain import KeychainError, read_generic_password
from family_recorder.listener import run_listener, validate_runtime_paths
from family_recorder.placement import run_placement_test
from family_recorder.storage import Storage
from family_recorder.summary import DailySummaryRunner

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
            read_generic_password(
                config.summary.keychain_service,
                config.summary.keychain_account,
            )
            print(f"[OK] Keychain service: {config.summary.keychain_service}")
        except KeychainError as exc:
            print(f"[MISSING] Keychain: {exc}")
            failed = True
    return int(failed)


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
