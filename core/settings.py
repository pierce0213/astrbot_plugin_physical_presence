"""把插件配置归一化成运行期设置，供 core 各模块共用。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


def _group(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = config.get(name) if isinstance(config, Mapping) else None
    return value if isinstance(value, Mapping) else {}


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "开启", "是"}
    if value is None:
        return default
    return bool(value)


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _str(value: Any, default: str, limit: int = 200) -> str:
    text = str(value if value is not None else default).strip()
    return text[:limit] if text else default


def _list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        items = [line.strip() for line in value.splitlines() if line.strip()]
        return items or list(default)
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or list(default)
    return list(default)


DEFAULT_PROPS = [
    "可乐 | 冰箱 | 冰 | 罐身挂着水珠",
    "汤碗 | 茶几 | 温 | 还剩半碗",
    "毛毯 | 沙发扶手 | 常温 | 叠着",
    "拖鞋 | 玄关 | 常温 |",
]

DEFAULT_FACTS = [
    "我们住在一起（我们的小别墅），每天见得到面",
    "和你说话时不用屏幕、消息、语音或视频中介",
    "她体寒，手脚容易凉",
    "家里有冰箱、厨房、院子，还有一只猫叫汤圆",
]


@dataclass
class RuntimeSettings:
    # 基础
    enable: bool = True
    label: str = "她"
    max_chars: int = 1200
    state_scope: str = "session"
    rewrite_injected: bool = True
    rewrite_reply: bool = True

    # 现场
    place: str = "客厅"
    detail: str = "沙发和茶几之间"
    her_pose: str = "盘腿坐在地毯上，背靠着沙发"
    distance_cm: int = 40
    indoor_temperature: str = "24°C"
    light_hint: str = ""
    user_state_mode: str = "unknown"  # unknown / assume_home

    # 她自己的日子
    life_enabled: bool = True
    life_source: str = "auto"  # auto / builtin / external
    identity: str = "学生"
    follow_mode: str = "together"  # together / home_only / separate
    vl_persona: str = ""
    include_underwear: bool = False

    # 物品
    initial_props: list[str] = field(default_factory=lambda: list(DEFAULT_PROPS))
    facts: list[str] = field(default_factory=lambda: list(DEFAULT_FACTS))
    contact_stale_minutes: int = 180
    cold_fade_minutes: int = 120

    # 动作
    force_action: bool = True
    action_history: int = 5
    output_tag: bool = True

    # 尺度与兜底
    intimacy_level: str = "日常"
    extra_banned: list[str] = field(default_factory=list)
    fallback_line: str = ""

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "RuntimeSettings":
        config = config or {}
        presence = _group(config, "presence_settings")
        props = _group(config, "props_settings")
        actions = _group(config, "action_settings")
        reality = _group(config, "reality_settings")
        intimacy = _group(config, "intimacy_settings")
        life = _group(config, "life_settings")

        scope = _str(presence.get("state_scope"), "session")
        if scope not in {"session", "global"}:
            scope = "session"

        level = _str(intimacy.get("level"), "日常")
        if level not in {"日常", "亲近"}:
            level = "日常"

        source = _str(life.get("source"), "auto")
        if source not in {"auto", "builtin", "external"}:
            source = "auto"

        follow = _str(life.get("follow_mode"), "together")
        if follow not in {"together", "home_only", "separate"}:
            follow = "together"

        user_mode = _str(presence.get("user_state_mode"), "unknown")
        if user_mode not in {"unknown", "assume_home"}:
            user_mode = "unknown"

        return cls(
            enable=_bool(presence.get("enable"), True),
            label=_str(presence.get("partner_label"), "她", 8),
            max_chars=_int(presence.get("max_chars"), 1200, 400, 4000),
            state_scope=scope,
            rewrite_injected=_bool(reality.get("rewrite_injected"), True),
            rewrite_reply=_bool(reality.get("rewrite_reply"), True),
            place=_str(presence.get("scene_place"), "客厅", 20),
            detail=_str(presence.get("scene_detail"), "沙发和茶几之间", 30),
            her_pose=_str(
                presence.get("her_pose"), "盘腿坐在地毯上，背靠着沙发", 60
            ),
            distance_cm=_int(presence.get("distance_cm"), 40, 0, 500),
            indoor_temperature=_str(presence.get("indoor_temperature"), "24°C", 8),
            light_hint=_str(presence.get("light_hint"), "", 40),
            user_state_mode=user_mode,
            life_enabled=_bool(life.get("enable"), True),
            life_source=source,
            identity=_str(life.get("identity"), "学生", 8),
            follow_mode=follow,
            vl_persona=_str(life.get("virtual_life_persona"), "", 40),
            include_underwear=_bool(life.get("include_underwear"), False),
            initial_props=_list(props.get("initial_props"), list(DEFAULT_PROPS)),
            facts=_list(props.get("facts"), list(DEFAULT_FACTS)),
            contact_stale_minutes=_int(
                props.get("contact_stale_minutes"), 180, 0, 1440
            ),
            cold_fade_minutes=_int(props.get("cold_fade_minutes"), 120, 0, 1440),
            force_action=_bool(actions.get("force_action"), True),
            action_history=_int(actions.get("action_history"), 5, 0, 20),
            output_tag=_bool(actions.get("output_tag"), True),
            intimacy_level=level,
            extra_banned=_list(reality.get("extra_banned_words"), []),
            fallback_line=_str(
                intimacy.get("fallback_line"),
                "",
                120,
            ),
        )
