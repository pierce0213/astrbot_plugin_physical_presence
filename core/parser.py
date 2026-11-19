"""解析模型输出：机器状态块、（）动作，以及没有状态块时的启发式推断。"""

from __future__ import annotations

import json
import re
from typing import Any

from .constants import FROM_STORAGE, PUT_DOWN, TAKE_TO_YOU
from .models import PresenceState

STATE_TAG_RE = re.compile(r"<\s*phys\s*>(.*?)<\s*/\s*phys\s*>", re.S | re.I)
STATE_COMMENT_RE = re.compile(r"<!--\s*PHYS\s*(.*?)\s*-->", re.S | re.I)
ACTION_RE = re.compile(r"[（(]([^（）()]{2,200})[）)]")
FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)

CONTACT_RE = re.compile(
    r"(?:她的|她)?"
    r"(手指|指尖|掌心|手背|手腕|手掌|脚踝|脚背|脚趾|膝盖|肩膀|脸侧|脸颊|额头|下巴|头发|手|脚|肩|脸)"
    r"(?:轻轻|慢慢|悄悄|试探着)?"
    r"(搭在|放在|贴在|握住|握|包住|捧住|扶住|搂住|牵着|拉着|蹭在|按在|贴着)"
    r"(?:你|你的)?"
    r"(脸侧|脸颊|脸|额头|手背|手腕|手心|掌心|手|脚踝|脚背|膝盖|膝|肩膀|肩|头发|头|腰|背|腿|怀里)"
)

DISTANCE_NEAR_RE = re.compile(r"挪近|靠近|凑近|探过身|挨着|坐到你旁边|往你那边挪")
DISTANCE_FAR_RE = re.compile(r"起身|走开|退开|站起|走进厨房|去厨房|走到冰箱|回房间")


def _loose_json(body: str) -> dict[str, Any]:
    text = body.strip()
    fence = FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    text = text.strip().strip("`").strip()
    text = (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
        .replace("，", ",")
    )
    text = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        value = json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            value = json.loads(text[start : end + 1])
        except Exception:
            return {}
    return value if isinstance(value, dict) else {}


def extract_state_block(text: str) -> tuple[str, dict[str, Any], bool]:
    """从回复里剥掉 <phys> 块，返回 (干净文本, 状态补丁, 是否存在状态块)。"""

    if not isinstance(text, str) or not text:
        return text or "", {}, False
    found = False
    patch: dict[str, Any] = {}
    clean = text

    for match in list(STATE_TAG_RE.finditer(text)) + list(STATE_COMMENT_RE.finditer(text)):
        found = True
        body = match.group(1).strip()
        if not body:
            continue
        parsed = _loose_json(body)
        if parsed:
            patch.update(parsed)
    clean = STATE_TAG_RE.sub("", clean)
    clean = STATE_COMMENT_RE.sub("", clean)
    clean = FENCE_RE.sub(lambda m: m.group(1) if m.group(1).strip().startswith(("{", "<")) else "", clean)
    clean = re.sub(r"[ \t]+\n", "\n", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, patch, found


def parse_actions(text: str) -> list[str]:
    if not isinstance(text, str):
        return []
    return [m.group(1).strip() for m in ACTION_RE.finditer(text) if m.group(1).strip()]


def heuristic_patch(text: str, state: PresenceState) -> dict[str, Any]:
    """模型没写状态块时，从动作文字里猜最明显的变化。

    只处理"看得见"的：东西递没递、喝没喝、距离远近、手搭在哪。
    猜错了也不会崩，下一轮状态块会纠正。
    """

    patch: dict[str, Any] = {}
    props_patch: list[dict[str, Any]] = []
    actions = parse_actions(text)
    if not actions:
        return patch

    for action in actions:
        for prop in state.props:
            if prop.name not in action and prop.uid not in action:
                continue
            if any(word in action for word in TAKE_TO_YOU):
                # “递到你手边”不等于他接了；只有明显塞进手里才算。
                if any(
                    word in action
                    for word in (
                        "塞进你手",
                        "放到你手",
                        "放在你手",
                        "塞到你手",
                        "交到你手",
                        "递到你手里",
                        "递到你手上",
                    )
                ):
                    if prop.holder != "you":
                        props_patch.append({"name": prop.name, "holder": "you"})
                elif prop.holder != "you":
                    props_patch.append({"name": prop.name, "holder": "her"})
                    patch["pending"] = f"把{prop.name}递过去，他还没接"
            elif any(word in action for word in PUT_DOWN):
                props_patch.append({"name": prop.name, "holder": "table"})
            elif any(word in action for word in FROM_STORAGE):
                if prop.holder not in {"you", "her"}:
                    props_patch.append({"name": prop.name, "holder": "her"})
            if "喝" in action and prop.holder == "you" and prop.level > 0.05:
                props_patch.append(
                    {"name": prop.name, "level": round(max(0.05, prop.level * 0.8), 2)}
                )

    if props_patch:
        # 同名物品按出现顺序去重，后写的覆盖先写的
        merged: dict[str, dict[str, Any]] = {}
        for item in props_patch:
            merged[item["name"]] = {**merged.get(item["name"], {}), **item}
        patch["props"] = list(merged.values())

    for action in actions:
        match = CONTACT_RE.search(action)
        if match:
            patch.setdefault("contact_add", []).append(
                {
                    "her": match.group(1),
                    "you": match.group(3),
                    "force": match.group(2),
                }
            )

    delta = 0
    if DISTANCE_NEAR_RE.search(text):
        delta -= 25
    if DISTANCE_FAR_RE.search(text):
        delta += 90
    if delta:
        patch["distance"] = max(0, min(500, int(state.distance_cm + delta)))

    return patch
