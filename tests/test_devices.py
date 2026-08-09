import pytest

from family_recorder.config import AudioConfig
from family_recorder.devices import (
    AudioDevice,
    AudioDeviceError,
    choose_input_device,
    select_input_device,
)

DEVICES = [
    AudioDevice(0, "MacBook Microphone", 1, 48_000),
    AudioDevice(2, "USB Audio Device", 2, 48_000),
    AudioDevice(4, "XMOS XVF3800 Voice Processor", 2, 48_000),
]


def test_auto_select_prefers_xvf3800() -> None:
    selected = choose_input_device(DEVICES, AudioConfig())
    assert selected.index == 4


def test_explicit_id_wins() -> None:
    selected = choose_input_device(DEVICES, AudioConfig(device_id=2))
    assert selected.index == 2


def test_default_input_is_not_silently_used() -> None:
    with pytest.raises(AudioDeviceError, match="No XVF3800"):
        choose_input_device([DEVICES[0]], AudioConfig(), default_input_index=0)


def test_default_input_must_be_opted_in() -> None:
    selected = choose_input_device(
        [DEVICES[0]],
        AudioConfig(allow_default_input=True),
        default_input_index=0,
    )
    assert selected.index == 0


def test_sounddevice_input_output_pair_is_supported() -> None:
    class InputOutputPair:
        def __getitem__(self, index: int) -> int:
            return [0, 8][index]

    class FakeSoundDevice:
        default = type("Default", (), {"device": InputOutputPair()})()

        @staticmethod
        def query_devices() -> list[dict[str, object]]:
            return [
                {
                    "name": "MacBook Microphone",
                    "max_input_channels": 1,
                    "default_samplerate": 48_000,
                }
            ]

    selected = select_input_device(
        AudioConfig(allow_default_input=True),
        sd_module=FakeSoundDevice,
    )
    assert selected.index == 0
