import struct
import time

from family_recorder.config import DirectionConfig
from family_recorder.direction import (
    DirectionSample,
    DirectionSampler,
    SpeechEnergySample,
    XVF3800USBReader,
    direction_for_interval,
    summarize_direction,
    summarize_speech_energy,
)


def _samples(*angles: float) -> list[DirectionSample]:
    return [DirectionSample(index * 250, angle, True) for index, angle in enumerate(angles)]


def test_usb_doa_response_contains_angle_and_speech_flag() -> None:
    response = bytes([0]) + struct.pack("<2H", 183, 1)
    assert XVF3800USBReader.decode_response(response) == (183.0, True)


def test_usb_speech_energy_response_contains_four_float_beams() -> None:
    response = bytes([0]) + struct.pack("<4f", 10.0, 20.0, 30.0, 40.0)
    assert XVF3800USBReader.decode_speech_energy_response(response) == (
        10.0,
        20.0,
        30.0,
        40.0,
    )


def test_output_route_recognizes_user_chosen_processed_auto_beam() -> None:
    route = XVF3800USBReader.decode_route_response(bytes([0, 8, 0]), "left")
    assert route.beamformed is True
    assert route.category == 8
    assert "auto-selected" in route.description


def test_output_route_does_not_mistake_raw_microphone_for_beamforming() -> None:
    route = XVF3800USBReader.decode_route_response(bytes([0, 3, 0]), "left")
    assert route.beamformed is False
    assert "raw/intermediate" in route.description


def test_speech_energy_summary_uses_auto_selected_beam_presence() -> None:
    summary = summarize_speech_energy(
        [
            SpeechEnergySample(0, 100, 0, 100, 100),
            SpeechEnergySample(250, 0, 0, 0, 0),
            SpeechEnergySample(500, 0, 200, 200, 200),
        ],
        DirectionConfig(),
    )
    assert summary.status == "speech"
    assert summary.speech_sample_count == 2
    assert summary.speech_ratio == 2 / 3
    assert summary.peak_auto_selected == 200
    assert summary.mean_auto_selected == 150


def test_sampler_aligns_doa_and_four_beams_on_one_offset() -> None:
    class FakeReader:
        @staticmethod
        def read() -> tuple[float, bool]:
            return 91.0, True

        @staticmethod
        def read_speech_energy() -> tuple[float, float, float, float]:
            return 10.0, 20.0, 30.0, 40.0

        def close(self) -> None:
            pass

    sampler = DirectionSampler(
        DirectionConfig(sample_interval_seconds=0.1, min_speech_samples=1),
        reader_factory=FakeReader,
    )
    sampler.start()
    time.sleep(0.03)
    capture = sampler.stop_acoustic()

    assert capture.samples
    sample = capture.samples[0]
    assert sample.raw_angle_degrees == 91
    assert sample.speech_detected is True
    assert sample.auto_selected_beam == 40
    assert capture.direction.samples[0].offset_ms == sample.offset_ms
    assert capture.speech_energy.samples[0].offset_ms == sample.offset_ms


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
