import struct

from family_recorder.config import DirectionConfig
from family_recorder.direction import (
    DirectionSample,
    XVF3800USBReader,
    direction_for_interval,
    summarize_direction,
)


def _samples(*angles: float) -> list[DirectionSample]:
    return [DirectionSample(index * 250, angle, True) for index, angle in enumerate(angles)]


def test_usb_doa_response_contains_angle_and_speech_flag() -> None:
    response = bytes([0]) + struct.pack("<2H", 183, 1)
    assert XVF3800USBReader.decode_response(response) == (183.0, True)


def test_direction_summary_handles_zero_degree_wraparound() -> None:
    summary = summarize_direction(
        _samples(355, 358, 2, 4),
        DirectionConfig(cluster_tolerance_degrees=20),
    )

    assert summary.status == "detected"
    assert summary.label == "正前方"
    assert summary.angle_degrees is not None
    assert summary.angle_degrees < 10 or summary.angle_degrees > 350
    assert summary.confidence == 1.0


def test_calibrated_front_rotates_room_direction_labels() -> None:
    summary = summarize_direction(
        _samples(88, 90, 92),
        DirectionConfig(front_angle_degrees=90),
    )

    assert summary.status == "detected"
    assert summary.label == "正前方"
    assert summary.raw_angle_degrees == 90
    assert summary.angle_degrees == 0


def test_separated_speech_directions_are_marked_multiple() -> None:
    summary = summarize_direction(
        _samples(88, 90, 92, 91, 268, 270, 272),
        DirectionConfig(
            cluster_tolerance_degrees=20,
            multiple_direction_min_ratio=0.25,
        ),
    )

    assert summary.status == "multiple"
    assert len(summary.clusters) == 2
    assert {cluster.label for cluster in summary.clusters} == {"左側", "右側"}


def test_interval_summary_uses_only_matching_direction_samples() -> None:
    whole = summarize_direction(
        [
            DirectionSample(0, 90, True),
            DirectionSample(250, 91, True),
            DirectionSample(1_000, 270, True),
            DirectionSample(1_250, 269, True),
        ],
        DirectionConfig(min_speech_samples=2, cluster_tolerance_degrees=20),
    )

    first = direction_for_interval(
        whole,
        DirectionConfig(min_speech_samples=2, cluster_tolerance_degrees=20),
        0,
        500,
    )
    assert first.status == "detected"
    assert first.label == "左側"
    assert [sample.offset_ms for sample in first.samples] == [0, 250]
