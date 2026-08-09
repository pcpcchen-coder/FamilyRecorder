from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from family_recorder.config import AppConfig


class ModelDownloadError(RuntimeError):
    """Raised when a local Whisper model cannot be downloaded safely."""


@dataclass(frozen=True)
class WhisperModelSpec:
    name: str
    display_name: str
    size_label: str
    approximate_bytes: int
    category: str
    description: str

    def as_menu_item(self, installed_names: set[str]) -> dict[str, object]:
        item = asdict(self)
        item["installed"] = self.name in installed_names
        return item


MIB = 1024 * 1024
GIB = 1024 * MIB
MIN_MODEL_BYTES = MIB
MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

# This multilingual allowlist mirrors whisper.cpp v1.8.1's official download script.
# English-only .en and tinydiarize models are intentionally excluded because the
# FamilyRecorder default language is Traditional Chinese.
WHISPER_MODEL_SPECS = (
    WhisperModelSpec("tiny", "Tiny", "約 75 MiB", 75 * MIB, "標準模型", "最快、準確度較低"),
    WhisperModelSpec("base", "Base", "約 142 MiB", 142 * MIB, "標準模型", "輕量入門"),
    WhisperModelSpec("small", "Small", "約 466 MiB", 466 * MIB, "標準模型", "速度優先"),
    WhisperModelSpec(
        "medium", "Medium", "約 1.5 GiB", int(1.5 * GIB), "標準模型", "品質與速度平衡"
    ),
    WhisperModelSpec(
        "large-v3-turbo",
        "Large v3 Turbo",
        "約 1.6 GiB",
        int(1.6 * GIB),
        "標準模型",
        "建議；中文品質佳",
    ),
    WhisperModelSpec(
        "large-v3", "Large v3", "約 2.9 GiB", int(2.9 * GIB), "標準模型", "最高品質、較慢"
    ),
    WhisperModelSpec("tiny-q5_1", "Tiny Q5", "約 31 MiB", 31 * MIB, "量化省空間", "最小容量"),
    WhisperModelSpec(
        "tiny-q8_0", "Tiny Q8", "約 42 MiB", 42 * MIB, "量化省空間", "輕量、較接近原版"
    ),
    WhisperModelSpec("base-q5_1", "Base Q5", "約 60 MiB", 60 * MIB, "量化省空間", "小容量"),
    WhisperModelSpec(
        "base-q8_0", "Base Q8", "約 78 MiB", 78 * MIB, "量化省空間", "輕量、較接近原版"
    ),
    WhisperModelSpec(
        "small-q5_1", "Small Q5", "約 190 MiB", 190 * MIB, "量化省空間", "推薦給容量有限的 Mac"
    ),
    WhisperModelSpec(
        "small-q8_0", "Small Q8", "約 252 MiB", 252 * MIB, "量化省空間", "品質較接近 Small"
    ),
    WhisperModelSpec(
        "medium-q5_0", "Medium Q5", "約 539 MiB", 539 * MIB, "量化省空間", "平衡、省容量"
    ),
    WhisperModelSpec(
        "medium-q8_0", "Medium Q8", "約 818 MiB", 818 * MIB, "量化省空間", "品質較接近 Medium"
    ),
    WhisperModelSpec(
        "large-v3-q5_0",
        "Large v3 Q5",
        "約 1.1 GiB",
        int(1.1 * GIB),
        "量化省空間",
        "高品質量化版",
    ),
    WhisperModelSpec(
        "large-v3-turbo-q5_0",
        "Large v3 Turbo Q5",
        "約 574 MiB",
        574 * MIB,
        "量化省空間",
        "建議的省空間版本",
    ),
    WhisperModelSpec(
        "large-v3-turbo-q8_0",
        "Large v3 Turbo Q8",
        "約 834 MiB",
        834 * MIB,
        "量化省空間",
        "品質較接近 Turbo 原版",
    ),
    WhisperModelSpec(
        "large-v1", "Large v1", "約 2.9 GiB", int(2.9 * GIB), "舊版相容", "第一代 Large"
    ),
    WhisperModelSpec(
        "large-v2", "Large v2", "約 2.9 GiB", int(2.9 * GIB), "舊版相容", "第二代 Large"
    ),
    WhisperModelSpec(
        "large-v2-q5_0",
        "Large v2 Q5",
        "約 1.1 GiB",
        int(1.1 * GIB),
        "舊版相容",
        "第二代 Large 量化版",
    ),
    WhisperModelSpec(
        "large-v2-q8_0",
        "Large v2 Q8",
        "約 1.5 GiB",
        int(1.5 * GIB),
        "舊版相容",
        "第二代 Large Q8",
    ),
)

MODEL_SPECS_BY_NAME = {spec.name: spec for spec in WHISPER_MODEL_SPECS}
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def model_name_from_path(path: Path) -> str:
    return path.stem.removeprefix("ggml-")


def downloadable_models(config: AppConfig) -> list[dict[str, object]]:
    models_dir = config.whisper.model_path.parent
    installed = {
        model_name_from_path(path) for path in models_dir.glob("ggml-*.bin") if path.is_file()
    }
    return [spec.as_menu_item(installed) for spec in WHISPER_MODEL_SPECS]


def is_valid_ggml_model(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < MIN_MODEL_BYTES:
        return False
    with path.open("rb") as model_file:
        return model_file.read(4) == b"lmgg"


def _curl_binary() -> str:
    discovered = shutil.which("curl")
    if discovered:
        return discovered
    if Path("/usr/bin/curl").is_file():
        return "/usr/bin/curl"
    raise ModelDownloadError("找不到 macOS curl，無法下載 Whisper 模型。")


def download_whisper_model(
    config: AppConfig,
    model_name: str,
    *,
    command_runner: CommandRunner = subprocess.run,
) -> tuple[Path, bool]:
    spec = MODEL_SPECS_BY_NAME.get(model_name)
    if spec is None:
        raise ModelDownloadError(f"不支援的 Whisper 模型：{model_name}")

    models_dir = config.whisper.model_path.parent
    models_dir.mkdir(parents=True, exist_ok=True)
    target = models_dir / f"ggml-{model_name}.bin"
    partial = models_dir / f".{target.name}.partial"
    if target.exists():
        if is_valid_ggml_model(target):
            return target.resolve(), False
        raise ModelDownloadError(f"模型檔存在但格式不完整：{target}")

    partial_size = partial.stat().st_size if partial.exists() else 0
    remaining = max(0, spec.approximate_bytes - partial_size)
    free_bytes = shutil.disk_usage(models_dir).free
    required = remaining + 256 * MIB
    if free_bytes < required:
        raise ModelDownloadError(
            f"磁碟空間不足；{spec.display_name} 還需要約 {spec.size_label}，"
            "並需保留至少 256 MiB 安全空間。"
        )

    url = f"{MODEL_BASE_URL}/ggml-{model_name}.bin"
    result = command_runner(
        [
            _curl_binary(),
            "--fail",
            "--location",
            "--silent",
            "--show-error",
            "--retry",
            "3",
            "--retry-delay",
            "2",
            "--continue-at",
            "-",
            "--output",
            str(partial),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "未知網路錯誤").strip()
        raise ModelDownloadError(f"模型下載失敗，可稍後重試並續傳：{detail}")
    if not is_valid_ggml_model(partial):
        partial.unlink(missing_ok=True)
        raise ModelDownloadError("下載完成但檔案格式驗證失敗，未套用此模型。")

    os.replace(partial, target)
    return target.resolve(), True
