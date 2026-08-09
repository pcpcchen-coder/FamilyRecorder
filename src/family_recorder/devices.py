from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Integral
from typing import Any

from family_recorder.config import AudioConfig


class AudioDeviceError(RuntimeError):
    """Raised when no suitable input device is available."""


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    input_channels: int
    default_sample_rate: float


def list_input_devices(sd_module: Any | None = None) -> list[AudioDevice]:
    if sd_module is None:
        import sounddevice as sd_module

    devices: list[AudioDevice] = []
    for index, raw in enumerate(sd_module.query_devices()):
        input_channels = int(raw.get("max_input_channels", 0))
        if input_channels <= 0:
            continue
        devices.append(
            AudioDevice(
                index=index,
                name=str(raw.get("name", f"device-{index}")),
                input_channels=input_channels,
                default_sample_rate=float(raw.get("default_samplerate", 0.0)),
            )
        )
    return devices


def _device_score(device: AudioDevice, requested_name: str) -> int:
    name = device.name.casefold()
    score = 0
    if requested_name and requested_name.casefold() in name:
        score += 1_000
    if "xvf3800" in name:
        score += 400
    if "xmos" in name:
        score += 250
    if "microphone array" in name or "mic array" in name:
        score += 100
    if "usb" in name:
        score += 40
    return score


def choose_input_device(
    devices: Iterable[AudioDevice],
    config: AudioConfig,
    default_input_index: int | None = None,
) -> AudioDevice:
    candidates = list(devices)
    if config.device_id is not None:
        for device in candidates:
            if device.index == config.device_id:
                return device
        raise AudioDeviceError(f"Configured input device id {config.device_id} was not found")

    scored = sorted(
        ((_device_score(device, config.device_name_contains), device) for device in candidates),
        key=lambda item: (-item[0], item[1].index),
    )
    if scored and scored[0][0] > 0:
        return scored[0][1]

    if config.allow_default_input and default_input_index is not None:
        for device in candidates:
            if device.index == default_input_index:
                return device

    available = ", ".join(f"[{device.index}] {device.name}" for device in candidates) or "none"
    raise AudioDeviceError(
        "No XVF3800/XMOS/USB microphone array matched the configuration. "
        f"Available inputs: {available}. Run `family-recorder list-devices` and set "
        "audio.device_id or audio.device_name_contains."
    )


def select_input_device(config: AudioConfig, sd_module: Any | None = None) -> AudioDevice:
    if sd_module is None:
        import sounddevice as sd_module

    default = getattr(sd_module.default, "device", (None, None))
    if isinstance(default, Integral):
        default_input = default
    else:
        try:
            default_input = default[0]
        except (IndexError, TypeError):
            default_input = None
    if not isinstance(default_input, Integral) or default_input < 0:
        default_input = None
    elif not isinstance(default_input, int):
        default_input = int(default_input)
    return choose_input_device(list_input_devices(sd_module), config, default_input)


def format_devices(devices: Iterable[AudioDevice]) -> str:
    rows = ["ID  Channels  Default Hz  Name"]
    rows.extend(
        f"{device.index:<3} {device.input_channels:<9} "
        f"{device.default_sample_rate:<11.0f} {device.name}"
        for device in devices
    )
    return "\n".join(rows)
