from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedValue:
    key: str | None
    value: Any
    display_value: str


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def normalize_state(provider_key: str, value: Any) -> NormalizedValue:
    """Normalize common traits while leaving unknown provider values untouched."""
    compact = _compact(provider_key)
    if compact.endswith(("onoff", "onofftraitonoff")) or compact in {
        "onoffon",
        "switch",
        "switch1",
        "switchled",
        "power",
    }:
        normalized = _as_bool(value)
        if normalized is not None:
            return NormalizedValue("on_off", normalized, "開啟" if normalized else "關閉")
    if "operationalstate" in compact or compact in {"workstate", "workstatus", "status"}:
        normalized = str(value).strip().casefold()
        labels = {
            "running": "運作中",
            "active": "運作中",
            "brewing": "沖煮中",
            "cooking": "烹調中",
            "heating": "加熱中",
            "paused": "已暫停",
            "stopped": "已停止",
            "inactive": "未運作",
            "off": "已關閉",
            "error": "錯誤",
        }
        return NormalizedValue("operational_state", normalized, labels.get(normalized, str(value)))
    if "fanspeed" in compact or "percentcurrent" in compact:
        return NormalizedValue("fan_speed", value, f"風速 {value}%")
    if "temperature" in compact:
        return NormalizedValue("temperature", value, f"溫度 {value}")
    if "connectivity" in compact or compact in {"online", "isonline"}:
        normalized = _as_bool(value)
        if normalized is not None:
            return NormalizedValue("connectivity", normalized, "連線" if normalized else "離線")
    return NormalizedValue(None, value, str(value))


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"on", "true", "1", "active"}:
            return True
        if lowered in {"off", "false", "0", "inactive"}:
            return False
    return None


def is_numeric_measurement(value: Any, normalized_key: str | None) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and normalized_key not in {"on_off", "connectivity"}
    )
