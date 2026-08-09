from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from family_recorder.config import SpeakerConfig

FEATURE_VERSION = 1
WINDOW_SECONDS = 3.0
WINDOW_HOP_SECONDS = 1.5


class SpeakerProfileError(RuntimeError):
    """Raised when a usable local speaker profile cannot be created or read."""


@dataclass(frozen=True)
class SpeakerProfile:
    name: str
    created_at: str
    sample_seconds: float
    vectors: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class SpeakerIdentification:
    label: str | None
    confidence: float | None
    status: str
    window_count: int
    vote_count: int = 0


def _profile_filename(name: str) -> str:
    digest = hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()[:20]
    return f"speaker-{digest}.json"


class SpeakerProfileStore:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "speaker-profiles"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)

    def path_for(self, name: str) -> Path:
        return self.directory / _profile_filename(name)

    def save(self, profile: SpeakerProfile) -> Path:
        path = self.path_for(profile.name)
        payload = {
            "feature_version": FEATURE_VERSION,
            "name": profile.name,
            "created_at": profile.created_at,
            "sample_seconds": round(profile.sample_seconds, 3),
            "vectors": [list(vector) for vector in profile.vectors],
        }
        handle, temporary = tempfile.mkstemp(prefix=".speaker-", dir=self.directory)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, separators=(",", ":"))
                output.write("\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return path

    def load(self, name: str) -> SpeakerProfile | None:
        path = self.path_for(name)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("feature_version") != FEATURE_VERSION:
                return None
            vectors = tuple(tuple(float(value) for value in row) for row in payload["vectors"])
            if not vectors or any(len(row) != len(vectors[0]) for row in vectors):
                raise ValueError("profile has no consistent feature vectors")
            return SpeakerProfile(
                name=str(payload["name"]),
                created_at=str(payload["created_at"]),
                sample_seconds=float(payload["sample_seconds"]),
                vectors=vectors,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SpeakerProfileError(f"Invalid speaker profile for {name}: {exc}") from exc

    def delete(self, name: str) -> bool:
        path = self.path_for(name)
        existed = path.exists()
        path.unlink(missing_ok=True)
        return existed

    def prune(self, members: tuple[str, ...]) -> int:
        keep = {_profile_filename(name) for name in members}
        removed = 0
        for path in self.directory.glob("speaker-*.json"):
            if path.name not in keep:
                path.unlink()
                removed += 1
        return removed

    def statuses(self, members: tuple[str, ...]) -> list[dict[str, object]]:
        statuses: list[dict[str, object]] = []
        for name in members:
            try:
                profile = self.load(name)
            except SpeakerProfileError:
                profile = None
            statuses.append(
                {
                    "name": name,
                    "enrolled": profile is not None,
                    "created_at": profile.created_at if profile else None,
                    "sample_seconds": profile.sample_seconds if profile else None,
                }
            )
        return statuses


def _pcm_samples(pcm16_mono: bytes) -> np.ndarray:
    samples = np.frombuffer(pcm16_mono, dtype=np.int16).astype(np.float64)
    if not samples.size:
        return samples
    samples /= 32768.0
    samples -= float(np.mean(samples))
    return samples


def _frames(samples: np.ndarray, frame_length: int, hop_length: int) -> np.ndarray:
    if len(samples) < frame_length:
        return np.empty((0, frame_length), dtype=np.float64)
    count = 1 + (len(samples) - frame_length) // hop_length
    shape = (count, frame_length)
    strides = (samples.strides[0] * hop_length, samples.strides[0])
    return np.lib.stride_tricks.as_strided(samples, shape=shape, strides=strides).copy()


def _mel_filterbank(sample_rate: int, fft_size: int, bands: int = 20) -> np.ndarray:
    minimum_hz = 80.0
    maximum_hz = min(4_000.0, sample_rate / 2)

    def to_mel(hz: float) -> float:
        return 2595.0 * math.log10(1.0 + hz / 700.0)

    def to_hz(mel: np.ndarray) -> np.ndarray:
        return 700.0 * (np.power(10.0, mel / 2595.0) - 1.0)

    mel_points = np.linspace(to_mel(minimum_hz), to_mel(maximum_hz), bands + 2)
    bins = np.floor((fft_size + 1) * to_hz(mel_points) / sample_rate).astype(int)
    bins = np.clip(bins, 0, fft_size // 2)
    filters = np.zeros((bands, fft_size // 2 + 1), dtype=np.float64)
    for band in range(bands):
        left, center, right = bins[band : band + 3]
        if center <= left:
            center = min(left + 1, fft_size // 2)
        if right <= center:
            right = min(center + 1, fft_size // 2)
        if center > left:
            filters[band, left:center] = np.arange(center - left) / (center - left)
        if right > center:
            filters[band, center:right] = np.arange(right - center, 0, -1) / (right - center)
    return filters


def _pitch_features(frames: np.ndarray, sample_rate: int) -> tuple[float, float, float]:
    if not len(frames):
        return 0.0, 0.0, 0.0
    min_lag = max(1, round(sample_rate / 400))
    max_lag = min(frames.shape[1] - 2, round(sample_rate / 70))
    pitches: list[float] = []
    strengths: list[float] = []
    for frame in frames[:: max(1, len(frames) // 80)]:
        centered = frame - np.mean(frame)
        energy = float(np.dot(centered, centered))
        if energy < 1e-6:
            continue
        correlation = np.correlate(centered, centered, mode="full")[len(centered) - 1 :]
        lag = min_lag + int(np.argmax(correlation[min_lag : max_lag + 1]))
        strength = float(correlation[lag] / max(correlation[0], 1e-12))
        if strength >= 0.2:
            pitches.append(sample_rate / lag)
            strengths.append(strength)
    if not pitches:
        return 0.0, 0.0, 0.0
    return (
        float(np.median(pitches)) / 400.0,
        float(np.subtract(*np.percentile(pitches, [75, 25]))) / 200.0,
        float(np.mean(strengths)),
    )


def extract_feature_vector(pcm16_mono: bytes, sample_rate: int) -> np.ndarray | None:
    """Create a compact timbre/pitch vector; it is an approximation, not biometrics."""
    samples = _pcm_samples(pcm16_mono)
    frame_length = max(128, round(sample_rate * 0.025))
    hop_length = max(64, round(sample_rate * 0.010))
    framed = _frames(samples, frame_length, hop_length)
    if len(framed) < 40:
        return None

    energy = np.sqrt(np.mean(np.square(framed), axis=1) + 1e-12)
    energy_db = 20 * np.log10(energy + 1e-12)
    threshold = max(-48.0, float(np.percentile(energy_db, 55)), float(np.max(energy_db) - 32))
    voiced = framed[energy_db >= threshold]
    if len(voiced) < 30:
        return None

    fft_size = 1 << (frame_length - 1).bit_length()
    windowed = voiced * np.hanning(frame_length)
    power = np.abs(np.fft.rfft(windowed, n=fft_size, axis=1)) ** 2
    filters = _mel_filterbank(sample_rate, fft_size)
    log_mel = np.log(np.maximum(power @ filters.T, 1e-12))
    log_mel -= np.mean(log_mel, axis=1, keepdims=True)
    mel_mean = np.mean(log_mel, axis=0)
    mel_std = np.std(log_mel, axis=0)

    frequencies = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
    spectrum_total = np.maximum(np.sum(power, axis=1), 1e-12)
    centroids = np.sum(power * frequencies, axis=1) / spectrum_total
    cumulative = np.cumsum(power, axis=1)
    rolloff_bins = np.argmax(cumulative >= (0.85 * spectrum_total[:, None]), axis=1)
    rolloffs = frequencies[rolloff_bins]
    zero_crossings = np.mean(np.abs(np.diff(np.signbit(voiced), axis=1)), axis=1)

    pitch_frames = _frames(samples, max(256, round(sample_rate * 0.050)), hop_length * 3)
    if len(pitch_frames):
        pitch_energy = np.sqrt(np.mean(np.square(pitch_frames), axis=1) + 1e-12)
        pitch_threshold = max(0.001, float(np.percentile(pitch_energy, 55)))
        pitch_frames = pitch_frames[pitch_energy >= pitch_threshold]
    pitch = _pitch_features(pitch_frames, sample_rate)
    extras = np.asarray(
        [
            *pitch,
            float(np.mean(centroids)) / 4_000.0,
            float(np.std(centroids)) / 2_000.0,
            float(np.mean(rolloffs)) / 4_000.0,
            float(np.std(rolloffs)) / 2_000.0,
            float(np.mean(zero_crossings)) * 4.0,
            float(np.std(zero_crossings)) * 8.0,
        ],
        dtype=np.float64,
    )
    vector = np.concatenate((mel_mean / 4.0, mel_std / 3.0, extras))
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm < 1e-9:
        return None
    return vector / norm


def feature_vectors(
    pcm16_mono: bytes,
    sample_rate: int,
    *,
    include_whole_sample: bool = False,
) -> list[np.ndarray]:
    samples = np.frombuffer(pcm16_mono, dtype=np.int16)
    window_samples = max(1, round(sample_rate * WINDOW_SECONDS))
    hop_samples = max(1, round(sample_rate * WINDOW_HOP_SECONDS))
    vectors: list[np.ndarray] = []
    if include_whole_sample:
        whole = extract_feature_vector(pcm16_mono, sample_rate)
        if whole is not None:
            vectors.append(whole)
    for offset in range(0, max(1, len(samples) - window_samples + 1), hop_samples):
        window = samples[offset : offset + window_samples]
        if len(window) < round(window_samples * 0.75):
            continue
        vector = extract_feature_vector(window.tobytes(), sample_rate)
        if vector is not None:
            vectors.append(vector)
    return vectors


def create_profile(name: str, pcm16_mono: bytes, sample_rate: int) -> SpeakerProfile:
    vectors = feature_vectors(pcm16_mono, sample_rate, include_whole_sample=True)
    if len(vectors) < 3:
        raise SpeakerProfileError("可用語音太少；請靠近麥克風，連續自然說話至少 10 秒後重試")
    return SpeakerProfile(
        name=name,
        created_at=datetime.now().astimezone().isoformat(),
        sample_seconds=len(pcm16_mono) / 2 / sample_rate,
        vectors=tuple(tuple(round(float(value), 8) for value in vector) for vector in vectors),
    )


def _cosine(first: np.ndarray, second: np.ndarray) -> float:
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator <= 1e-12:
        return -1.0
    return float(np.dot(first, second) / denominator)


def identify_speaker(
    pcm16_mono: bytes,
    sample_rate: int,
    profiles: list[SpeakerProfile],
    config: SpeakerConfig,
) -> SpeakerIdentification:
    if not config.enabled or not profiles:
        return SpeakerIdentification(None, None, "disabled", 0)
    vectors = feature_vectors(pcm16_mono, sample_rate)
    if not vectors:
        return SpeakerIdentification(None, None, "uncertain", 0)

    prepared = {
        profile.name: [np.asarray(vector, dtype=np.float64) for vector in profile.vectors]
        for profile in profiles
    }
    votes: list[tuple[str, float]] = []
    for vector in vectors:
        scores = sorted(
            (
                (name, max(_cosine(vector, sample) for sample in samples))
                for name, samples in prepared.items()
            ),
            key=lambda value: value[1],
            reverse=True,
        )
        winner, top_score = scores[0]
        runner_up = scores[1][1] if len(scores) > 1 else -1.0
        if top_score >= config.min_similarity and top_score - runner_up >= config.min_margin:
            votes.append((winner, top_score))

    if not votes:
        return SpeakerIdentification(None, None, "uncertain", len(vectors))
    counts: dict[str, int] = {}
    for name, _score in votes:
        counts[name] = counts.get(name, 0) + 1
    winner = max(counts, key=counts.get)  # type: ignore[arg-type]
    winner_votes = counts[winner]
    dominance = winner_votes / len(vectors)
    confidence = float(np.mean([score for name, score in votes if name == winner]))
    if dominance < config.dominance_threshold:
        status = "mixed" if len(counts) > 1 else "uncertain"
        return SpeakerIdentification(None, confidence, status, len(vectors), winner_votes)
    return SpeakerIdentification(winner, confidence, "recognized", len(vectors), winner_votes)
