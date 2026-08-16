from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime

from family_recorder.config import SmartHomeConfig, StorageConfig
from family_recorder.home.store import HomeStateStore, capability_is_allowed


@dataclass(frozen=True)
class HomeTimelineItem:
    account_id: str
    device_id: str
    capability_key: str
    device_name: str
    room_name: str
    state_label: str
    started_at: datetime
    ended_at: datetime | None
    time_quality: str


def _active_state(normalized_key: str | None, value: object) -> str | None:
    if normalized_key == "on_off" and value is True:
        return "運作"
    if normalized_key == "operational_state" and str(value).casefold() in {
        "running",
        "active",
        "brewing",
        "cooking",
        "heating",
    }:
        labels = {
            "brewing": "沖煮",
            "cooking": "烹調",
            "heating": "加熱",
        }
        return labels.get(str(value).casefold(), "運作")
    return None


def _format_time(item: HomeTimelineItem) -> str:
    start = item.started_at.strftime("%H:%M")
    if item.ended_at and item.ended_at > item.started_at:
        return f"{start}–{item.ended_at:%H:%M}"
    return start


def _merge(items: list[HomeTimelineItem], gap_seconds: int) -> list[HomeTimelineItem]:
    merged: list[HomeTimelineItem] = []
    for item in items:
        if not merged:
            merged.append(item)
            continue
        previous = merged[-1]
        same_signal = (
            previous.account_id == item.account_id
            and previous.device_id == item.device_id
            and previous.capability_key == item.capability_key
            and previous.state_label == item.state_label
        )
        if previous.ended_at and same_signal:
            gap = (item.started_at - previous.ended_at).total_seconds()
            if 0 <= gap <= gap_seconds:
                merged[-1] = replace(previous, ended_at=item.ended_at or previous.ended_at)
                continue
        merged.append(item)
    return merged


def timeline_items(
    storage: StorageConfig, config: SmartHomeConfig, target: date
) -> list[HomeTimelineItem]:
    if not config.enabled:
        return []
    with HomeStateStore(storage) as store:
        rows = store.events_for_date(target)
    items: list[HomeTimelineItem] = []
    for row in rows:
        if not capability_is_allowed(
            config.summary_allowlist,
            str(row["account_id"]),
            str(row["provider_device_id"]),
            str(row["provider_capability_key"]),
        ):
            continue
        value = json.loads(str(row["normalized_value_json"]))
        state_label = _active_state(row["normalized_capability_key"], value)
        if state_label is None:
            continue
        items.append(
            HomeTimelineItem(
                account_id=str(row["account_id"]),
                device_id=str(row["provider_device_id"]),
                capability_key=str(row["provider_capability_key"]),
                device_name=str(row["device_name"]),
                room_name=str(row["room_name"] or ""),
                state_label=state_label,
                started_at=datetime.fromisoformat(str(row["started_at"])),
                ended_at=(
                    datetime.fromisoformat(str(row["ended_at"])) if row["ended_at"] else None
                ),
                time_quality=str(row["time_quality"]),
            )
        )
    return _merge(items, config.merge_gap_seconds)


def render_home_timeline(storage: StorageConfig, config: SmartHomeConfig, target: date) -> str:
    items = timeline_items(storage, config, target)
    if not items:
        return ""
    lines = ["## 本機智慧家庭事件時間線"]
    for item in items:
        location = f"{item.room_name}／" if item.room_name else ""
        if item.ended_at:
            event_text = f"{item.device_name}{item.state_label}"
        elif item.state_label == "運作":
            event_text = f"{item.device_name}開啟"
        else:
            event_text = f"{item.device_name}{item.state_label}開始"
        time_note = (
            ""
            if item.time_quality in {"provider", "provider_history"}
            else "（以本機觀測時間記錄）"
        )
        lines.append(f"- {_format_time(item)}｜{location}{event_text}{time_note}")
    return "\n".join(lines)
