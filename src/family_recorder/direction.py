from __future__ import annotations

import math
import struct
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

from family_recorder.config import DirectionConfig

XVF3800_VENDOR_ID = 0x2886
XVF3800_PRODUCT_ID = 0x001A
USB_VENDOR_DEVICE_IN = 0xC0
DOA_RESOURCE_ID = 20
DOA_COMMAND_ID = 18
AEC_RESOURCE_ID = 33
SPEECH_ENERGY_COMMAND_ID = 80
AUDIO_MANAGER_RESOURCE_ID = 35
AUDIO_MANAGER_LEFT_COMMAND_ID = 15
AUDIO_MANAGER_RIGHT_COMMAND_ID = 19
CONTROL_SUCCESS = 0
CONTROL_RETRY = 64


class DirectionError(RuntimeError):
    """Raised when XVF3800 direction telemetry cannot be read."""


@dataclass(frozen=True)
class DirectionSample:
    offset_ms: int
    raw_angle_degrees: float
    speech_detected: bool


@dataclass(frozen=True)
class SpeechEnergySample:
    offset_ms: int
    focused_beam_1: float
    focused_beam_2: float
    free_running_beam: float
    auto_selected_beam: float


@dataclass(frozen=True)
class SpeechEnergySummary:
    status: str
    speech_sample_count: int
    total_sample_count: int
    speech_ratio: float
    peak_auto_selected: float | None
    mean_auto_selected: float | None
    samples: tuple[SpeechEnergySample, ...]
    error: str | None = None


@dataclass(frozen=True)
class AcousticSample:
    offset_ms: int
    raw_angle_degrees: float | None
    speech_detected: bool | None
    focused_beam_1: float | None
    focused_beam_2: float | None
    free_running_beam: float | None
    auto_selected_beam: float | None


@dataclass(frozen=True)
class AcousticCapture:
    direction: DirectionSummary
    speech_energy: SpeechEnergySummary
    samples: tuple[AcousticSample, ...]


@dataclass(frozen=True)
class OutputRoute:
    channel: str
    category: int
    source: int
    description: str
    beamformed: bool
    asr_or_aec_residual: bool


@dataclass(frozen=True)
class DirectionCluster:
    raw_angle_degrees: float
    angle_degrees: float
    label: str
    sample_count: int
    ratio: float


@dataclass(frozen=True)
class DirectionSummary:
    status: str
    raw_angle_degrees: float | None
    angle_degrees: float | None
    label: str | None
    confidence: float | None
    spread_degrees: float | None
    speech_sample_count: int
    total_sample_count: int
    clusters: tuple[DirectionCluster, ...]
    samples: tuple[DirectionSample, ...]
    error: str | None = None


class DirectionReader(Protocol):
    def read(self) -> tuple[float, bool]: ...

    def read_speech_energy(self) -> tuple[float, float, float, float]: ...

    def close(self) -> None: ...


class XVF3800USBReader:
    """Read the XVF3800 DOA_VALUE vendor command over its USB control interface."""

    def __init__(
        self,
        *,
        timeout_ms: int = 1_000,
        usb_core: Any | None = None,
        usb_util: Any | None = None,
    ) -> None:
        if usb_core is None or usb_util is None:
            import usb.core as usb_core_module
            import usb.util as usb_util_module

            usb_core = usb_core_module
            usb_util = usb_util_module
        self._usb_util = usb_util
        self._timeout_ms = timeout_ms
        self._device = usb_core.find(
            idVendor=XVF3800_VENDOR_ID,
            idProduct=XVF3800_PRODUCT_ID,
        )
        if self._device is None:
            raise DirectionError("找不到 XVF3800 USB 控制介面（VID 2886、PID 001A）")

    @staticmethod
    def decode_response(response: bytes) -> tuple[float, bool]:
        if len(response) != 5:
            raise DirectionError(f"XVF3800 DOA 回應長度不正確：{len(response)}")
        status = response[0]
        if status != CONTROL_SUCCESS:
            raise DirectionError(f"XVF3800 DOA 回應狀態異常：{status}")
        angle, speech = struct.unpack("<2H", response[1:])
        return float(angle % 360), bool(speech)

    def _read_control(self, resource_id: int, command_id: int, response_length: int) -> bytes:
        response: bytes | None = None
        for attempt in range(4):
            raw = self._device.ctrl_transfer(
                USB_VENDOR_DEVICE_IN,
                0,
                0x80 | command_id,
                resource_id,
                response_length,
                self._timeout_ms,
            )
            response = bytes(raw)
            if response and response[0] == CONTROL_RETRY and attempt < 3:
                time.sleep(0.01)
                continue
            break
        if response is None:
            raise DirectionError("XVF3800 沒有回傳控制資料")
        return response

    def read(self) -> tuple[float, bool]:
        response = self._read_control(DOA_RESOURCE_ID, DOA_COMMAND_ID, 5)
        return self.decode_response(response)

    @staticmethod
    def decode_speech_energy_response(
        response: bytes,
    ) -> tuple[float, float, float, float]:
        if len(response) != 17:
            raise DirectionError(f"XVF3800 speech-energy 回應長度不正確：{len(response)}")
        status = response[0]
        if status != CONTROL_SUCCESS:
            raise DirectionError(f"XVF3800 speech-energy 回應狀態異常：{status}")
        return struct.unpack("<4f", response[1:])

    def read_speech_energy(self) -> tuple[float, float, float, float]:
        response = self._read_control(AEC_RESOURCE_ID, SPEECH_ENERGY_COMMAND_ID, 17)
        return self.decode_speech_energy_response(response)

    @staticmethod
    def decode_route_response(response: bytes, channel: str) -> OutputRoute:
        if len(response) != 3:
            raise DirectionError(f"XVF3800 {channel} routing 回應長度不正確：{len(response)}")
        status, category, source = response
        if status != CONTROL_SUCCESS:
            raise DirectionError(f"XVF3800 {channel} routing 回應狀態異常：{status}")
        if category == 6:
            source_names = {
                0: "slow focused beam 1",
                1: "slow focused beam 2",
                2: "fast/free-running beam",
                3: "auto-selected best beam",
            }
            description = f"processed beamformed: {source_names.get(source, f'source {source}')}"
        elif category == 7:
            description = f"AEC residual / ASR beam {source}"
        elif category == 8:
            description = (
                "user-chosen channel copying processed auto-selected beam"
                if source in {0, 1}
                else f"user-chosen channel source {source}"
            )
        elif category in {1, 2, 3, 11}:
            description = f"raw/intermediate microphone category {category}, source {source}"
        elif category == 0:
            description = "silence"
        else:
            description = f"audio mux category {category}, source {source}"
        return OutputRoute(
            channel=channel,
            category=category,
            source=source,
            description=description,
            beamformed=(category == 6 and source in range(4))
            or (category == 8 and source in {0, 1}),
            asr_or_aec_residual=category == 7 and source in range(4),
        )

    def read_output_routes(self) -> tuple[OutputRoute, OutputRoute]:
        left = self.decode_route_response(
            self._read_control(
                AUDIO_MANAGER_RESOURCE_ID,
                AUDIO_MANAGER_LEFT_COMMAND_ID,
                3,
            ),
            "left",
        )
        right = self.decode_route_response(
            self._read_control(
                AUDIO_MANAGER_RESOURCE_ID,
                AUDIO_MANAGER_RIGHT_COMMAND_ID,
                3,
            ),
            "right",
        )
        return left, right

    def close(self) -> None:
        self._usb_util.dispose_resources(self._device)


def normalize_angle(angle: float) -> float:
    return angle % 360.0


def angular_distance(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def circular_mean(angles: list[float]) -> float:
    if not angles:
        raise ValueError("circular_mean requires at least one angle")
    radians = [math.radians(value) for value in angles]
    sine = sum(math.sin(value) for value in radians)
    cosine = sum(math.cos(value) for value in radians)
    if abs(sine) < 1e-12 and abs(cosine) < 1e-12:
        return normalize_angle(angles[0])
    return normalize_angle(math.degrees(math.atan2(sine, cosine)))


def direction_label(angle_degrees: float) -> str:
    labels = (
        "正前方",
        "左前方",
        "左側",
        "左後方",
        "正後方",
        "右後方",
        "右側",
        "右前方",
    )
    return labels[int((normalize_angle(angle_degrees) + 22.5) // 45.0) % 8]


def _cluster_angles(angles: list[float], tolerance: float) -> list[list[float]]:
    clusters: list[list[float]] = []
    for angle in angles:
        if not clusters:
            clusters.append([angle])
            continue
        distances = [angular_distance(angle, circular_mean(cluster)) for cluster in clusters]
        closest = min(range(len(clusters)), key=distances.__getitem__)
        if distances[closest] <= tolerance:
            clusters[closest].append(angle)
        else:
            clusters.append([angle])

    merged = True
    while merged and len(clusters) > 1:
        merged = False
        for first_index in range(len(clusters)):
            for second_index in range(first_index + 1, len(clusters)):
                if (
                    angular_distance(
                        circular_mean(clusters[first_index]),
                        circular_mean(clusters[second_index]),
                    )
                    <= tolerance
                ):
                    clusters[first_index].extend(clusters.pop(second_index))
                    merged = True
                    break
            if merged:
                break
    return sorted(clusters, key=len, reverse=True)


def summarize_direction(
    samples: list[DirectionSample] | tuple[DirectionSample, ...],
    config: DirectionConfig,
    *,
    error: str | None = None,
) -> DirectionSummary:
    sample_tuple = tuple(samples)
    if not config.enabled:
        return DirectionSummary("disabled", None, None, None, None, None, 0, 0, (), ())
    speech_samples = [sample for sample in sample_tuple if sample.speech_detected]
    if not speech_samples:
        status = "unavailable" if error and not sample_tuple else "uncertain"
        return DirectionSummary(
            status,
            None,
            None,
            None,
            None,
            None,
            0,
            len(sample_tuple),
            (),
            sample_tuple,
            error,
        )
    if len(speech_samples) < config.min_speech_samples:
        return DirectionSummary(
            "uncertain",
            None,
            None,
            None,
            None,
            None,
            len(speech_samples),
            len(sample_tuple),
            (),
            sample_tuple,
            error,
        )

    angle_clusters = _cluster_angles(
        [sample.raw_angle_degrees for sample in speech_samples],
        config.cluster_tolerance_degrees,
    )
    total = len(speech_samples)
    clusters: list[DirectionCluster] = []
    for values in angle_clusters:
        raw_angle = circular_mean(values)
        room_angle = normalize_angle(raw_angle - config.front_angle_degrees)
        clusters.append(
            DirectionCluster(
                raw_angle,
                room_angle,
                direction_label(room_angle),
                len(values),
                len(values) / total,
            )
        )

    primary = clusters[0]
    primary_values = angle_clusters[0]
    spread = sum(
        angular_distance(value, primary.raw_angle_degrees) for value in primary_values
    ) / len(primary_values)
    multiple = any(
        cluster.ratio >= config.multiple_direction_min_ratio
        and angular_distance(cluster.raw_angle_degrees, primary.raw_angle_degrees)
        >= max(60.0, config.cluster_tolerance_degrees * 1.5)
        for cluster in clusters[1:]
    )
    return DirectionSummary(
        "multiple" if multiple else "detected",
        primary.raw_angle_degrees,
        primary.angle_degrees,
        primary.label,
        primary.ratio,
        spread,
        total,
        len(sample_tuple),
        tuple(clusters),
        sample_tuple,
        error,
    )


def direction_for_interval(
    summary: DirectionSummary,
    config: DirectionConfig,
    start_ms: int,
    end_ms: int,
) -> DirectionSummary:
    selected = [
        DirectionSample(
            max(0, sample.offset_ms - start_ms),
            sample.raw_angle_degrees,
            sample.speech_detected,
        )
        for sample in summary.samples
        if start_ms <= sample.offset_ms < end_ms
    ]
    return summarize_direction(selected, config, error=summary.error)


def summarize_speech_energy(
    samples: list[SpeechEnergySample] | tuple[SpeechEnergySample, ...],
    config: DirectionConfig,
    *,
    error: str | None = None,
) -> SpeechEnergySummary:
    sample_tuple = tuple(samples)
    if not config.enabled or not config.speech_energy_enabled:
        return SpeechEnergySummary("disabled", 0, 0, 0.0, None, None, (), error)
    if not sample_tuple:
        return SpeechEnergySummary("unavailable", 0, 0, 0.0, None, None, (), error)
    speech_values = [
        sample.auto_selected_beam
        for sample in sample_tuple
        if sample.auto_selected_beam > config.speech_energy_threshold
    ]
    count = len(speech_values)
    total = len(sample_tuple)
    return SpeechEnergySummary(
        "speech" if count else "silence",
        count,
        total,
        count / total,
        max(speech_values) if speech_values else 0.0,
        sum(speech_values) / count if speech_values else 0.0,
        sample_tuple,
        error,
    )


ReaderFactory = Callable[[], DirectionReader]


class DirectionSampler:
    def __init__(
        self,
        config: DirectionConfig,
        *,
        reader_factory: ReaderFactory | None = None,
    ) -> None:
        self.config = config
        self.reader_factory = reader_factory or (
            lambda: XVF3800USBReader(timeout_ms=config.usb_timeout_ms)
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = 0.0
        self._samples: list[DirectionSample] = []
        self._speech_energy_samples: list[SpeechEnergySample] = []
        self._acoustic_samples: list[AcousticSample] = []
        self._direction_error: str | None = None
        self._speech_energy_error: str | None = None
        self._capture: AcousticCapture | None = None

    def start(self) -> None:
        if not self.config.enabled or self._thread is not None:
            return
        self._started_at = time.monotonic()
        self._thread = threading.Thread(
            target=self._run,
            name="familyrecorder-xvf3800-doa",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        reader: DirectionReader | None = None
        try:
            reader = self.reader_factory()
            while not self._stop.is_set():
                offset_ms = round((time.monotonic() - self._started_at) * 1_000)
                angle: float | None = None
                speech: bool | None = None
                energy: tuple[float, float, float, float] | None = None
                try:
                    angle, speech = reader.read()
                    angle = normalize_angle(angle)
                    self._samples.append(DirectionSample(offset_ms, angle, speech))
                except Exception as exc:
                    self._direction_error = str(exc)[-500:]
                if self.config.speech_energy_enabled:
                    try:
                        energy = reader.read_speech_energy()
                        self._speech_energy_samples.append(SpeechEnergySample(offset_ms, *energy))
                    except Exception as exc:
                        self._speech_energy_error = str(exc)[-500:]
                if angle is not None or energy is not None:
                    self._acoustic_samples.append(
                        AcousticSample(
                            offset_ms,
                            angle,
                            speech,
                            energy[0] if energy else None,
                            energy[1] if energy else None,
                            energy[2] if energy else None,
                            energy[3] if energy else None,
                        )
                    )
                self._stop.wait(self.config.sample_interval_seconds)
        except Exception as exc:
            error = str(exc)[-500:]
            self._direction_error = error
            self._speech_energy_error = error
        finally:
            if reader is not None:
                with suppress(Exception):
                    reader.close()

    def stop_acoustic(self) -> AcousticCapture:
        if self._capture is not None:
            return self._capture
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.config.usb_timeout_ms / 1_000 + 1.0))
        self._capture = AcousticCapture(
            summarize_direction(
                self._samples,
                self.config,
                error=self._direction_error,
            ),
            summarize_speech_energy(
                self._speech_energy_samples,
                self.config,
                error=self._speech_energy_error,
            ),
            tuple(self._acoustic_samples),
        )
        return self._capture

    def stop(self) -> DirectionSummary:
        return self.stop_acoustic().direction


def capture_direction(
    config: DirectionConfig,
    seconds: float,
    *,
    reader_factory: ReaderFactory | None = None,
) -> DirectionSummary:
    sampler = DirectionSampler(config, reader_factory=reader_factory)
    sampler.start()
    time.sleep(max(0.0, seconds))
    return sampler.stop()
