from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import asdict, fields, replace
from datetime import date
from pathlib import Path

from family_recorder.config import (
    DEFAULT_SUMMARY_PROMPT,
    HALLUCINATION_FILTER_PRESETS,
    AppConfig,
    HallucinationFilterConfig,
    load_config,
    validate_config,
)
from family_recorder.config_editor import update_yaml_scalar, update_yaml_value
from family_recorder.control import pause_recording, read_pause_state, resume_recording
from family_recorder.devices import format_devices, list_input_devices, select_input_device
from family_recorder.direction import OutputRoute, XVF3800USBReader, capture_direction
from family_recorder.home.bridge import load_companion_payload
from family_recorder.home.fake import FakeHomeProvider
from family_recorder.home.service import HomeSyncService
from family_recorder.home.store import HomeStateStore
from family_recorder.listener import run_listener, validate_runtime_paths
from family_recorder.model_manager import download_whisper_model, downloadable_models
from family_recorder.placement import run_placement_test
from family_recorder.speakers import SpeakerProfileStore, create_profile
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
    download_model = commands.add_parser(
        "download-whisper-model", help="Download, verify, and select a multilingual model"
    )
    download_model.add_argument("--model", required=True)
    summary_model = commands.add_parser(
        "set-summary-model", help="Select a Codex summary model; empty uses the account default"
    )
    summary_model.add_argument("--model", required=True)
    summary_prompt = commands.add_parser(
        "set-summary-prompt", help="Set the editable instructions used for ChatGPT summaries"
    )
    summary_prompt.add_argument("--prompt", required=True)
    commands.add_parser("reset-summary-prompt", help="Restore the built-in summary instructions")
    commands.add_parser("menu-status", help=argparse.SUPPRESS)

    home_fixture = commands.add_parser(
        "home-sync-fixture", help="Import a fake smart-home provider fixture for local testing"
    )
    home_fixture.add_argument("--fixture", type=Path, required=True)
    home_bridge = commands.add_parser(
        "home-ingest-companion",
        help="Import a credential-free payload from a signed mobile companion",
    )
    home_bridge.add_argument("--file", type=Path, required=True)
    home_capability = commands.add_parser(
        "set-home-capability",
        help="Allow one discovered device capability to be recorded or summarized",
    )
    home_capability.add_argument("--scope", choices=("record", "summary"), required=True)
    home_capability.add_argument("--selection-key", required=True)
    home_capability.add_argument("--capability", required=True)
    home_capability.add_argument("--enabled", choices=("true", "false"), required=True)
    home_disconnect = commands.add_parser(
        "disconnect-home-account", help="Disconnect a provider while retaining local history"
    )
    home_disconnect.add_argument("--account-id", required=True)
    commands.add_parser("home-status", help="Show local smart-home connection and privacy status")

    hallucination_preset = commands.add_parser(
        "set-hallucination-preset",
        help="Select relaxed, balanced, or strict anti-hallucination thresholds",
    )
    hallucination_preset.add_argument(
        "--name",
        choices=tuple(HALLUCINATION_FILTER_PRESETS),
        required=True,
    )
    hallucination = commands.add_parser(
        "set-hallucination-filter",
        help="Adjust local acoustic and Whisper hallucination thresholds",
    )
    boolean_filter_fields = (
        "enabled",
        "hardware_silence_guard_enabled",
        "adaptive_noise_enabled",
        "low_frequency_filter_enabled",
        "whisper_confidence_enabled",
        "suppress_non_speech_tokens",
        "repeat_filter_enabled",
    )
    for name in boolean_filter_fields:
        hallucination.add_argument(
            f"--{name.replace('_', '-')}",
            choices=("true", "false"),
            dest=name,
        )
    integer_filter_fields = (
        "noise_window_chunks",
        "noise_min_samples",
        "repeat_window_seconds",
        "max_repetitions",
        "min_repeat_text_chars",
    )
    for name in integer_filter_fields:
        hallucination.add_argument(
            f"--{name.replace('_', '-')}",
            type=int,
            dest=name,
        )
    numeric_filter_fields = (
        "hardware_silence_max_ratio",
        "hardware_silence_max_software_speech_ratio",
        "hardware_silence_max_snr_db",
        "noise_margin_db",
        "low_frequency_min_ratio",
        "tonal_energy_min_ratio",
        "no_speech_probability_max",
        "min_avg_logprob",
        "low_probability_threshold",
        "max_low_probability_ratio",
        "max_compression_ratio",
        "repeat_similarity_threshold",
    )
    for name in numeric_filter_fields:
        hallucination.add_argument(
            f"--{name.replace('_', '-')}",
            type=float,
            dest=name,
        )

    common_terms = commands.add_parser(
        "set-common-terms", help="Set words and names used to improve local transcription"
    )
    common_terms.add_argument("--term", action="append", default=[])

    speakers = commands.add_parser(
        "set-speakers", help="Set the known household members for approximate local labeling"
    )
    speakers.add_argument("--name", action="append", default=[])
    enroll = commands.add_parser(
        "enroll-speaker", help="Record a temporary sample and save only its local voice features"
    )
    enroll.add_argument("--name", required=True)
    enroll.add_argument("--seconds", type=int, default=15)
    enroll.add_argument("--delay", type=float, default=2.0)
    delete_profile = commands.add_parser(
        "delete-speaker-profile", help="Delete one locally stored voice feature profile"
    )
    delete_profile.add_argument("--name", required=True)

    direction_enabled = commands.add_parser(
        "set-direction-enabled", help="Enable or disable XVF3800 direction telemetry"
    )
    direction_enabled.add_argument("--enabled", choices=("true", "false"), required=True)
    calibrate_direction = commands.add_parser(
        "calibrate-direction", help="Use the current speaking position as room front (0 degrees)"
    )
    calibrate_direction.add_argument("--seconds", type=float, default=4.0)
    probe_direction = commands.add_parser(
        "probe-direction", help="Sample and display XVF3800 direction telemetry"
    )
    probe_direction.add_argument("--seconds", type=float, default=2.0)
    beamforming = commands.add_parser(
        "diagnose-beamforming",
        help="Verify that the captured UAC channel is beamformed/processed",
    )
    beamforming.add_argument("--json", action="store_true", dest="as_json")

    calendar_enabled = commands.add_parser(
        "set-calendar-enabled", help="Enable or pause Google Calendar candidate extraction"
    )
    calendar_enabled.add_argument("--enabled", choices=("true", "false"), required=True)
    calendar_auto_create = commands.add_parser(
        "set-calendar-auto-create",
        help="Automatically create extracted events after one-time user opt-in",
    )
    calendar_auto_create.add_argument("--enabled", choices=("true", "false"), required=True)
    calendar_default = commands.add_parser(
        "set-calendar-default", help="Select the default writable Google Calendar"
    )
    calendar_default.add_argument("--calendar-id", required=True)
    calendar_default.add_argument("--calendar-name", required=True)
    member_calendar = commands.add_parser(
        "set-member-calendar", help="Assign or unassign a calendar for one household member"
    )
    member_calendar.add_argument("--member", required=True)
    member_calendar.add_argument("--calendar-id", required=True)
    member_calendar.add_argument("--calendar-name", default="")
    member_calendar.add_argument("--enabled", choices=("true", "false"), required=True)
    member_calendar_default = commands.add_parser(
        "set-member-calendar-default", help="Select one assigned default calendar for a member"
    )
    member_calendar_default.add_argument("--member", required=True)
    member_calendar_default.add_argument("--calendar-id", required=True)
    calendar_created = commands.add_parser(
        "calendar-event-created", help="Mark a confirmed calendar candidate as created"
    )
    calendar_created.add_argument("--id", type=int, required=True)
    calendar_created.add_argument("--external-id", default="")
    calendar_dismissed = commands.add_parser(
        "dismiss-calendar-event", help="Dismiss a pending calendar candidate"
    )
    calendar_dismissed.add_argument("--id", type=int, required=True)

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
    if config.direction.enabled:
        reader = None
        try:
            reader = XVF3800USBReader(timeout_ms=config.direction.usb_timeout_ms)
            angle, speech = reader.read()
            energy = reader.read_speech_energy()
            left, right = reader.read_output_routes()
            print(
                f"[OK] XVF3800 direction telemetry: raw {angle:.0f} degrees, "
                f"speech={'yes' if speech else 'no'}"
            )
            print("[OK] XVF3800 speech energy: " + ", ".join(f"{value:.1f}" for value in energy))
            print(
                f"[{'OK' if left.beamformed else 'WARN'}] UAC left routing: "
                f"({left.category}, {left.source}) {left.description}"
            )
            print(f"[OK] UAC right routing: ({right.category}, {right.source}) {right.description}")
            if config.audio.channels != 1:
                print(
                    "[WARN] audio.channels is not 1; stereo downmix cannot verify "
                    "the processed left channel"
                )
                failed = True
            elif not left.beamformed:
                failed = True
        except Exception as exc:
            print(f"[MISSING] XVF3800 direction telemetry: {exc}")
            failed = True
        finally:
            if reader is not None:
                with suppress(Exception):
                    reader.close()
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


def _route_dict(route: OutputRoute) -> dict[str, object]:
    return {
        "channel": route.channel,
        "category": route.category,
        "source": route.source,
        "description": route.description,
        "beamformed": route.beamformed,
        "asr_or_aec_residual": route.asr_or_aec_residual,
    }


def _beamforming_diagnostic(config: AppConfig) -> dict[str, object]:
    device = select_input_device(config.audio)
    reader = XVF3800USBReader(timeout_ms=config.direction.usb_timeout_ms)
    try:
        left, right = reader.read_output_routes()
    finally:
        reader.close()
    captured_channels = min(config.audio.channels, device.input_channels)
    if captured_channels == 1:
        verified = left.beamformed
        capture_mode = "left"
        verdict = (
            "verified_beamformed_processed" if verified else "unexpected_non_beamformed_left_route"
        )
    else:
        verified = False
        capture_mode = "downmix_left_and_right"
        verdict = "ambiguous_stereo_downmix"
    return {
        "device": {
            "index": device.index,
            "name": device.name,
            "input_channels": device.input_channels,
            "sample_rate": device.default_sample_rate,
        },
        "configured_channels": config.audio.channels,
        "captured_channels": captured_channels,
        "capture_mode": capture_mode,
        "routes": {"left": _route_dict(left), "right": _route_dict(right)},
        "verified": verified,
        "verdict": verdict,
    }


def _print_beamforming_diagnostic(report: dict[str, object]) -> None:
    device = report["device"]
    routes = report["routes"]
    assert isinstance(device, dict)
    assert isinstance(routes, dict)
    left = routes["left"]
    right = routes["right"]
    assert isinstance(left, dict)
    assert isinstance(right, dict)
    print(f"Audio device: [{device['index']}] {device['name']}")
    print(f"Left route: ({left['category']}, {left['source']}) {left['description']}")
    print(f"Right route: ({right['category']}, {right['source']}) {right['description']}")
    print(f"Capture mode: {report['capture_mode']}")
    if report["verified"]:
        print("[OK] FamilyRecorder is capturing the beamformed/processed left UAC channel.")
    else:
        print(f"[WARN] Beamformed capture is not verified: {report['verdict']}")


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
    profile_store = SpeakerProfileStore(data_dir)
    with Storage(config.storage) as storage:
        hallucination_stats = storage.hallucination_filter_stats(today)
        pending_calendar_events = [
            {
                "id": candidate.id,
                "summary_date": candidate.summary_date,
                "title": candidate.title,
                "starts_at": candidate.starts_at,
                "ends_at": candidate.ends_at,
                "all_day": candidate.all_day,
                "notes": candidate.notes,
                "member_name": candidate.member_name,
                "suggested_calendar_id": candidate.suggested_calendar_id,
            }
            for candidate in storage.pending_calendar_candidates()
        ]
    smart_home_status = _smart_home_status(config)
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
        "downloadable_whisper_models": downloadable_models(config),
        "summary_model": config.summary.model,
        "summary_prompt": config.summary.prompt,
        "common_terms": list(config.whisper.common_terms),
        "hallucination_filter": asdict(config.hallucination_filter),
        "hallucination_filter_preset": next(
            (
                name
                for name, preset in HALLUCINATION_FILTER_PRESETS.items()
                if preset == config.hallucination_filter
            ),
            "custom",
        ),
        "hallucination_filter_stats": hallucination_stats,
        "speaker_enabled": config.speakers.enabled,
        "speaker_members": profile_store.statuses(config.speakers.members),
        "speaker_profiles_dir": str(profile_store.directory),
        "direction_enabled": config.direction.enabled,
        "direction_front_angle_degrees": config.direction.front_angle_degrees,
        "calendar_enabled": config.calendar.enabled,
        "calendar_auto_create": config.calendar.auto_create,
        "calendar_provider": config.calendar.provider,
        "calendar_default_id": config.calendar.default_calendar_id,
        "calendar_default_name": config.calendar.default_calendar_name,
        "calendar_names": config.calendar.calendar_names,
        "calendar_member_ids": {
            member: list(calendar_ids)
            for member, calendar_ids in config.calendar.member_calendar_ids.items()
        },
        "calendar_member_default_ids": config.calendar.member_default_calendar_ids,
        "calendar_pending_events": pending_calendar_events,
        "smart_home": smart_home_status,
    }


def _smart_home_status(config: AppConfig) -> dict[str, object]:
    with HomeStateStore(config.storage) as store:
        accounts = store.account_statuses()
        devices = store.device_statuses(config.smart_home)
    stored_account_ids = {str(account["id"]) for account in accounts}
    accounts.extend(
        {
            "id": account.id,
            "provider": account.provider,
            "display_name": account.display_name or account.id,
            "transport": account.transport,
            "status": "disconnected",
            "message": "尚未完成第一次同步",
            "requires_reauthorization": False,
            "last_checked_at": None,
            "last_success_at": None,
            "retry_at": None,
        }
        for account in config.smart_home.accounts
        if account.id not in stored_account_ids
    )
    failures = [
        account
        for account in accounts
        if account["status"] in {"error", "degraded", "reauthorization_required"}
    ]
    last_successes = [
        str(account["last_success_at"]) for account in accounts if account.get("last_success_at")
    ]
    if not config.smart_home.enabled:
        status = "disabled"
    elif not accounts:
        status = "not_connected"
    elif failures:
        status = "attention"
    elif any(account["status"] == "connected" for account in accounts):
        status = "connected"
    else:
        status = "disconnected"
    return {
        "enabled": config.smart_home.enabled,
        "status": status,
        "last_updated_at": max(last_successes, default=""),
        "accounts": accounts,
        "devices": devices,
        "errors": [str(account["message"]) for account in failures if account["message"]],
        "google_native_macos_supported": False,
        "google_connection_path": "signed_ios_or_android_companion_bridge",
    }


def _set_allowlist_value(
    mapping: dict[str, tuple[str, ...]],
    selection: str,
    capability: str,
    enabled: bool,
) -> dict[str, tuple[str, ...]]:
    updated = {key: tuple(values) for key, values in mapping.items()}
    values = list(updated.get(selection, ()))
    if enabled and capability not in values:
        values.append(capability)
    if not enabled and capability in values:
        values.remove(capability)
    if values:
        updated[selection] = tuple(sorted(values))
    else:
        updated.pop(selection, None)
    return updated


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
        if args.command == "home-sync-fixture":
            provider = FakeHomeProvider.from_path(args.fixture.expanduser().resolve())
            result = asyncio.run(
                HomeSyncService(config.storage, config.smart_home).sync_once(provider)
            )
            print(
                "智慧家庭測試資料已同步："
                f"事件 {result.events_inserted}、快照 {result.snapshots_inserted}、"
                f"去重 {result.duplicates_skipped}、合併 {result.coalesced}、"
                f"隱私規則略過 {result.policy_skipped}"
            )
            return 0
        if args.command == "home-ingest-companion":
            batch = load_companion_payload(args.file.expanduser().resolve())
            with HomeStateStore(config.storage) as store:
                result = store.record_batch(batch, config.smart_home)
            print(
                "Companion 狀態已匯入："
                f"事件 {result.events_inserted}、快照 {result.snapshots_inserted}、"
                f"隱私規則略過 {result.policy_skipped}"
            )
            return 0
        if args.command == "home-status":
            print(json.dumps(_smart_home_status(config), ensure_ascii=False, indent=2))
            return 0
        if args.command == "set-home-capability":
            selection = args.selection_key.strip()
            capability = args.capability.strip()
            if (
                not selection
                or not capability
                or any(character in selection + capability for character in ("\n", "\r"))
            ):
                raise ValueError("智慧家庭裝置與屬性識別不可空白或包含換行")
            status = _smart_home_status(config)
            discovered = {
                (device["selection_key"], item["key"])
                for device in status["devices"]
                for item in device["capabilities"]
            }
            if (selection, capability) not in discovered:
                raise ValueError("找不到已探索的智慧家庭裝置屬性")
            enabled = args.enabled == "true"
            record_allowlist = dict(config.smart_home.record_allowlist)
            summary_allowlist = dict(config.smart_home.summary_allowlist)
            if args.scope == "record":
                record_allowlist = _set_allowlist_value(
                    record_allowlist, selection, capability, enabled
                )
                if not enabled:
                    summary_allowlist = _set_allowlist_value(
                        summary_allowlist, selection, capability, False
                    )
            else:
                summary_allowlist = _set_allowlist_value(
                    summary_allowlist, selection, capability, enabled
                )
                if enabled:
                    record_allowlist = _set_allowlist_value(
                        record_allowlist, selection, capability, True
                    )
            smart_home = replace(
                config.smart_home,
                enabled=True,
                record_allowlist=record_allowlist,
                summary_allowlist=summary_allowlist,
            )
            validate_config(replace(config, smart_home=smart_home))
            config_path = args.config.expanduser().resolve()
            update_yaml_value(config_path, "smart_home", "enabled", True)
            update_yaml_value(
                config_path,
                "smart_home",
                "record_allowlist",
                {key: list(values) for key, values in record_allowlist.items()},
            )
            update_yaml_value(
                config_path,
                "smart_home",
                "summary_allowlist",
                {key: list(values) for key, values in summary_allowlist.items()},
            )
            print("智慧家庭隱私 allowlist 已更新")
            return 0
        if args.command == "disconnect-home-account":
            account_id = args.account_id.strip()
            if not account_id:
                raise ValueError("智慧家庭 account ID 不可空白")
            accounts = tuple(
                account for account in config.smart_home.accounts if account.id != account_id
            )
            removed_from_config = len(accounts) != len(config.smart_home.accounts)
            prefix = f"{account_id}/"
            record_allowlist = {
                key: values
                for key, values in config.smart_home.record_allowlist.items()
                if not key.startswith(prefix)
            }
            summary_allowlist = {
                key: values
                for key, values in config.smart_home.summary_allowlist.items()
                if not key.startswith(prefix)
            }
            with HomeStateStore(config.storage) as store:
                disconnected = store.disconnect_account(account_id)
            if not disconnected and not removed_from_config:
                raise ValueError("找不到這個智慧家庭連線")
            config_path = args.config.expanduser().resolve()
            update_yaml_value(
                config_path,
                "smart_home",
                "accounts",
                [asdict(account) for account in accounts],
            )
            update_yaml_value(
                config_path,
                "smart_home",
                "record_allowlist",
                {key: list(values) for key, values in record_allowlist.items()},
            )
            update_yaml_value(
                config_path,
                "smart_home",
                "summary_allowlist",
                {key: list(values) for key, values in summary_allowlist.items()},
            )
            print("智慧家庭連線已移除；本機歷史事件仍保留")
            return 0
        if args.command == "diagnose-beamforming":
            report = _beamforming_diagnostic(config)
            if args.as_json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                _print_beamforming_diagnostic(report)
            return 0 if report["verified"] else 1
        if args.command == "set-whisper-model":
            model_path = args.path.expanduser().resolve()
            if not model_path.is_file():
                raise FileNotFoundError(f"Whisper model not found: {model_path}")
            update_yaml_scalar(
                args.config.expanduser().resolve(), "whisper", "model_path", str(model_path)
            )
            print(f"Whisper model: {_model_name(model_path)}")
            return 0
        if args.command == "download-whisper-model":
            model_path, downloaded = download_whisper_model(config, args.model)
            update_yaml_scalar(
                args.config.expanduser().resolve(), "whisper", "model_path", str(model_path)
            )
            action = "Downloaded and selected" if downloaded else "Selected existing"
            print(f"{action} Whisper model: {_model_name(model_path)}")
            return 0
        if args.command == "set-summary-model":
            update_yaml_scalar(
                args.config.expanduser().resolve(), "summary", "model", args.model.strip()
            )
            print(f"Summary model: {args.model.strip() or 'ChatGPT account default'}")
            return 0
        if args.command in {"set-summary-prompt", "reset-summary-prompt"}:
            prompt = (
                args.prompt.strip()
                if args.command == "set-summary-prompt"
                else DEFAULT_SUMMARY_PROMPT
            )
            if not prompt:
                raise ValueError("摘要 Prompt 不可空白")
            if len(prompt) > 20_000:
                raise ValueError("摘要 Prompt 最多 20,000 個字元")
            update_yaml_value(args.config.expanduser().resolve(), "summary", "prompt", prompt)
            message = (
                "摘要 Prompt 已恢復內建預設"
                if args.command == "reset-summary-prompt"
                else "摘要 Prompt 已儲存"
            )
            print(message)
            return 0
        if args.command == "set-hallucination-preset":
            preset = HALLUCINATION_FILTER_PRESETS[args.name]
            config_path = args.config.expanduser().resolve()
            for item in fields(HallucinationFilterConfig):
                update_yaml_value(
                    config_path,
                    "hallucination_filter",
                    item.name,
                    getattr(preset, item.name),
                )
            print(f"防幻覺過濾已切換為 {args.name}")
            return 0
        if args.command == "set-hallucination-filter":
            boolean_names = {
                "enabled",
                "hardware_silence_guard_enabled",
                "adaptive_noise_enabled",
                "low_frequency_filter_enabled",
                "whisper_confidence_enabled",
                "suppress_non_speech_tokens",
                "repeat_filter_enabled",
            }
            updates: dict[str, object] = {}
            for item in fields(HallucinationFilterConfig):
                value = getattr(args, item.name, None)
                if value is not None:
                    updates[item.name] = value == "true" if item.name in boolean_names else value
            if not updates:
                raise ValueError("至少要提供一個防幻覺設定")
            updated_filter = replace(config.hallucination_filter, **updates)
            validate_config(replace(config, hallucination_filter=updated_filter))
            config_path = args.config.expanduser().resolve()
            for name, value in updates.items():
                update_yaml_value(config_path, "hallucination_filter", name, value)
            print("防幻覺過濾門檻已更新")
            return 0
        if args.command == "set-common-terms":
            terms = tuple(term.strip() for term in args.term if term.strip())
            if len(terms) > 100:
                raise ValueError("常用字詞最多可設定 100 個")
            if any(len(term) > 40 or "\n" in term or "\r" in term for term in terms):
                raise ValueError("每個常用字詞必須是 1 到 40 個字元")
            if len({term.casefold() for term in terms}) != len(terms):
                raise ValueError("常用字詞不可重複")
            update_yaml_value(
                args.config.expanduser().resolve(), "whisper", "common_terms", list(terms)
            )
            print(f"常用字詞已設定為 {len(terms)} 個")
            return 0
        if args.command == "set-speakers":
            members = tuple(name.strip() for name in args.name if name.strip())
            if len(members) > 8:
                raise ValueError("家庭成員最多可設定 8 人")
            if len({name.casefold() for name in members}) != len(members):
                raise ValueError("家庭成員姓名不可重複")
            if any(len(name) > 80 or "\n" in name or "\r" in name for name in members):
                raise ValueError("家庭成員姓名格式不正確")
            config_path = args.config.expanduser().resolve()
            update_yaml_value(config_path, "speakers", "members", list(members))
            update_yaml_value(config_path, "speakers", "enabled", bool(members))
            removed = SpeakerProfileStore(config.storage.data_dir).prune(members)
            suffix = f"；已刪除 {removed} 個不再使用的聲音樣本" if removed else ""
            print(f"家庭成員已設定為 {len(members)} 人{suffix}")
            return 0
        if args.command == "enroll-speaker":
            if args.name not in config.speakers.members:
                raise ValueError("請先把這個姓名加入家庭成員清單")
            if args.seconds < 10 or args.seconds > 60:
                raise ValueError("註冊錄音長度必須在 10 到 60 秒之間")
            if args.delay < 0 or args.delay > 10:
                raise ValueError("錄音延遲必須在 0 到 10 秒之間")
            if _listener_is_running() and not read_pause_state(config.storage.data_dir).paused:
                raise RuntimeError("錄音服務仍在執行；請先暫停錄音再註冊聲音")
            if args.delay:
                time.sleep(args.delay)
            from family_recorder.audio import AudioRecorder

            recorder = AudioRecorder(config.audio)
            with recorder.open_stream() as stream:
                chunk = recorder.read_chunk(stream, seconds=args.seconds)
            profile = create_profile(args.name, chunk.pcm16_mono, chunk.sample_rate)
            SpeakerProfileStore(config.storage.data_dir).save(profile)
            print(f"{args.name} 的聲音樣本已建立；暫存錄音未保存")
            return 0
        if args.command == "delete-speaker-profile":
            if args.name not in config.speakers.members:
                raise ValueError("找不到這位家庭成員")
            deleted = SpeakerProfileStore(config.storage.data_dir).delete(args.name)
            print("聲音樣本已刪除" if deleted else "這位成員尚未建立聲音樣本")
            return 0
        if args.command == "set-direction-enabled":
            enabled = args.enabled == "true"
            update_yaml_value(args.config.expanduser().resolve(), "direction", "enabled", enabled)
            print("方向判斷已開啟" if enabled else "方向判斷已關閉")
            return 0
        if args.command == "set-calendar-enabled":
            enabled = args.enabled == "true"
            if enabled and not config.calendar.default_calendar_id:
                raise ValueError("請先選擇預設 Google Calendar")
            update_yaml_value(args.config.expanduser().resolve(), "calendar", "enabled", enabled)
            print("Google Calendar 候選事件已開啟" if enabled else "Google Calendar 候選事件已暫停")
            return 0
        if args.command == "set-calendar-auto-create":
            enabled = args.enabled == "true"
            if enabled and not config.calendar.enabled:
                raise ValueError("請先開啟 Google Calendar 候選事件")
            if enabled and not config.calendar.default_calendar_id:
                raise ValueError("請先選擇預設 Google Calendar")
            update_yaml_value(
                args.config.expanduser().resolve(), "calendar", "auto_create", enabled
            )
            print("摘要後將自動加入行事曆" if enabled else "已恢復逐筆確認模式")
            return 0
        if args.command == "set-calendar-default":
            calendar_id = args.calendar_id.strip()
            calendar_name = args.calendar_name.strip()
            if not calendar_id or not calendar_name:
                raise ValueError("Google Calendar ID 與名稱不可空白")
            config_path = args.config.expanduser().resolve()
            update_yaml_value(config_path, "calendar", "provider", "google")
            update_yaml_value(config_path, "calendar", "default_calendar_id", calendar_id)
            update_yaml_value(config_path, "calendar", "default_calendar_name", calendar_name)
            calendar_names = dict(config.calendar.calendar_names)
            calendar_names[calendar_id] = calendar_name
            update_yaml_value(config_path, "calendar", "calendar_names", calendar_names)
            update_yaml_value(config_path, "calendar", "enabled", True)
            print(f"預設 Google Calendar：{calendar_name}")
            return 0
        if args.command == "set-member-calendar":
            if args.member not in config.speakers.members:
                raise ValueError("找不到這位家庭成員")
            calendar_id = args.calendar_id.strip()
            if not calendar_id:
                raise ValueError("Calendar ID 不可空白")
            mappings = {
                member: list(calendar_ids)
                for member, calendar_ids in config.calendar.member_calendar_ids.items()
            }
            assigned = mappings.setdefault(args.member, [])
            enabled = args.enabled == "true"
            if enabled and calendar_id not in assigned:
                assigned.append(calendar_id)
            if not enabled and calendar_id in assigned:
                assigned.remove(calendar_id)
            if not assigned:
                mappings.pop(args.member, None)
            defaults = dict(config.calendar.member_default_calendar_ids)
            calendar_names = dict(config.calendar.calendar_names)
            if args.calendar_name.strip():
                calendar_names[calendar_id] = args.calendar_name.strip()
            if enabled and args.member not in defaults:
                defaults[args.member] = calendar_id
            if not enabled and defaults.get(args.member) == calendar_id:
                if assigned:
                    defaults[args.member] = assigned[0]
                else:
                    defaults.pop(args.member, None)
            config_path = args.config.expanduser().resolve()
            update_yaml_value(config_path, "calendar", "member_calendar_ids", mappings)
            update_yaml_value(config_path, "calendar", "member_default_calendar_ids", defaults)
            update_yaml_value(config_path, "calendar", "calendar_names", calendar_names)
            print("家庭成員日曆對應已更新")
            return 0
        if args.command == "set-member-calendar-default":
            assigned = config.calendar.member_calendar_ids.get(args.member, ())
            if args.calendar_id not in assigned:
                raise ValueError("請先把這個日曆指派給該家庭成員")
            defaults = dict(config.calendar.member_default_calendar_ids)
            defaults[args.member] = args.calendar_id
            update_yaml_value(
                args.config.expanduser().resolve(),
                "calendar",
                "member_default_calendar_ids",
                defaults,
            )
            print("家庭成員預設日曆已更新")
            return 0
        if args.command in {"calendar-event-created", "dismiss-calendar-event"}:
            with Storage(config.storage) as storage:
                updated = storage.mark_calendar_candidate(
                    args.id,
                    "created" if args.command == "calendar-event-created" else "dismissed",
                    external_event_id=(
                        args.external_id if args.command == "calendar-event-created" else ""
                    ),
                )
            if not updated:
                raise ValueError("找不到待確認的行事曆事件")
            print(
                "行事曆事件已建立" if args.command == "calendar-event-created" else "候選事件已略過"
            )
            return 0
        if args.command in {"calibrate-direction", "probe-direction"}:
            if not 1 <= args.seconds <= 15:
                raise ValueError("方向取樣時間必須在 1 到 15 秒之間")
            direction_config = replace(config.direction, enabled=True)
            result = capture_direction(direction_config, args.seconds)
            if result.status == "unavailable":
                raise RuntimeError(f"無法讀取 XVF3800 方向：{result.error}")
            if result.status == "uncertain":
                raise RuntimeError("沒有取得足夠的連續語音方向；請持續說話後重試")
            if result.status == "multiple":
                detail = "、".join(
                    f"{cluster.label} {cluster.angle_degrees:.0f}°"
                    for cluster in result.clusters[:3]
                )
                raise RuntimeError(f"同時偵測到多個方向（{detail}）；請只讓一個人在正前方說話")
            assert result.raw_angle_degrees is not None
            if args.command == "calibrate-direction":
                raw_angle = round(result.raw_angle_degrees, 1)
                update_yaml_value(
                    args.config.expanduser().resolve(),
                    "direction",
                    "front_angle_degrees",
                    raw_angle,
                )
                update_yaml_value(args.config.expanduser().resolve(), "direction", "enabled", True)
                print(f"方向正前方已校準：XVF3800 原始角度 {raw_angle:.1f}°")
            else:
                print(
                    f"方向：{result.label} {result.angle_degrees:.0f}°；"
                    f"原始角度 {result.raw_angle_degrees:.0f}°；"
                    f"穩定度 {(result.confidence or 0):.0%}；"
                    f"語音樣本 {result.speech_sample_count}/{result.total_sample_count}"
                )
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
