"""读取 astrbot_plugin_virtual_life 的 plans.json：日程、穿搭、主动窗口。

不修改它、不依赖它的内部类，只按 JSON 结构取数据。
读不到就完全静默，由内置"她的一天"兜底。
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

CATEGORY_LABELS = {
    "hairstyle": "发型",
    "headwear": "头饰",
    "top": "上装",
    "bottom": "下装",
    "outerwear": "外套",
    "legwear": "袜子",
    "shoes": "鞋",
    "accessory": "配饰",
    "bag": "包",
    "makeup": "妆容",
    "fragrance": "气味",
    "other": "随身",
    "underwear": "打底",
    "underpants": "打底",
}

HIDDEN_CATEGORIES = {"underwear", "underpants"}


def _norm(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return "".join(
        ch
        for ch in value
        if not ch.isspace() and not unicodedata.category(ch).startswith("P")
    )


def _minute(hhmm: str) -> int:
    try:
        hour, minute = str(hhmm).split(":")[:2]
        return int(hour) * 60 + int(minute)
    except (TypeError, ValueError):
        return 0


class VirtualLifeReader:
    def __init__(self, data_dir: Path | None) -> None:
        self.path = Path(data_dir) / "plans.json" if data_dir else None
        self._mtime: float = -1.0
        self._data: dict[str, Any] = {}

    def available(self) -> bool:
        return bool(self.path and self.path.exists())

    def load(self) -> dict[str, Any]:
        if not self.available():
            return {}
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return {}
        if mtime != self._mtime:
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
                self._mtime = mtime
            except (OSError, json.JSONDecodeError, TypeError):
                self._data = {}
        return self._data if isinstance(self._data, dict) else {}

    def find_plan(
        self,
        today: str,
        activity_hint: str = "",
        persona_id: str = "",
    ) -> dict[str, Any] | None:
        plans = self.load().get("plans") or {}
        if not isinstance(plans, dict):
            return None

        candidates: list[tuple[str, dict[str, Any]]] = [
            (key, value)
            for key, value in plans.items()
            if isinstance(value, dict)
            and (value.get("date") == today or key.startswith(f"{today}::"))
        ]
        if not candidates:
            return None

        if persona_id:
            for key, value in candidates:
                if key.endswith(f"::{persona_id}") or value.get("persona_id") == persona_id:
                    return value

        hint = _norm(activity_hint)
        if hint:
            best: tuple[int, dict[str, Any]] | None = None
            for _, plan in candidates:
                for block in plan.get("timeline") or []:
                    activity = _norm(block.get("activity") or "")
                    if not activity:
                        continue
                    if activity in hint or hint in activity:
                        score = len(activity)
                        if best is None or score > best[0]:
                            best = (score, plan)
            if best:
                return best[1]

        # 兜底：取今天最后一个（通常是当前正在用的人格）
        candidates.sort(key=lambda item: item[0])
        return candidates[-1][1]

    @staticmethod
    def block_at(plan: dict[str, Any] | None, now: datetime) -> dict[str, Any] | None:
        if not plan:
            return None
        current = now.hour * 60 + now.minute
        for block in plan.get("timeline") or []:
            start = _minute(block.get("start"))
            end = _minute(block.get("end"))
            if end == 0 and str(block.get("end")) == "24:00":
                end = 24 * 60
            if start <= end:
                if start <= current < end:
                    return block
            elif current >= start or current < end:
                return block
        return None

    @staticmethod
    def next_block(plan: dict[str, Any] | None, now: datetime) -> dict[str, Any] | None:
        if not plan:
            return None
        current = now.hour * 60 + now.minute
        upcoming = [
            block
            for block in plan.get("timeline") or []
            if _minute(block.get("start")) > current
        ]
        if not upcoming:
            return None
        return min(upcoming, key=lambda block: _minute(block.get("start")))

    @staticmethod
    def outfit_text(plan: dict[str, Any] | None, include_underwear: bool = False) -> str:
        if not plan:
            return ""
        outfit = plan.get("outfit") or {}
        if not isinstance(outfit, dict):
            return ""
        summary = str(outfit.get("summary") or "").strip().rstrip("。")
        pieces: list[str] = []
        for item in outfit.get("items") or []:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "")
            if category in HIDDEN_CATEGORIES and not include_underwear:
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            label = CATEGORY_LABELS.get(category, "其他")
            pieces.append(f"{label}：{name}")
        text = summary
        if pieces:
            text = (text + "。" if text else "") + "；".join(pieces[:10])
        return text[:260]

    @staticmethod
    def proactive_windows(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not plan:
            return []
        windows = plan.get("proactive_windows") or []
        return [item for item in windows if isinstance(item, dict)]
