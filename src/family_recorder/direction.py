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

    def read(self) -> tuple[float, bool]:
        response: bytes | None = None
        for attempt in range(4):
            raw = self._device.ctrl_transfer(
                USB_VENDOR_DEVICE_IN,
                0,
                0x80 | DOA_COMMAND_ID,
                DOA_RESOURCE_ID,
                5,
                self._timeout_ms,
            )
            response = bytes(raw)
            if response and response[0] == CONTROL_RETRY and attempt < 3:
                time.sleep(0.01)
                continue
            break
        if response is None:
            raise DirectionError("XVF3800 沒有回傳 DOA 資料")
        return self.decode_response(response)

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
        self._error: str | None = None

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
                angle, speech = reader.read()
                self._samples.append(
                    DirectionSample(
                        round((time.monotonic() - self._started_at) * 1_000),
                        normalize_angle(angle),
                        speech,
                    )
                )
                self._stop.wait(self.config.sample_interval_seconds)
        except Exception as exc:
            self._error = str(exc)[-500:]
        finally:
            if reader is not None:
                with suppress(Exception):
                    reader.close()

    def stop(self) -> DirectionSummary:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.config.usb_timeout_ms / 1_000 + 1.0))
        return summarize_direction(self._samples, self.config, error=self._error)


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
