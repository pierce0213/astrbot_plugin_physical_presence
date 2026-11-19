"""把物理现场渲染成模型能读的 <physical_state>，以及人看的现场卡。"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .constants import HOLDER_LABELS, HOLDER_ORDER
from .models import PresenceState, Prop
from .settings import RuntimeSettings


def period_words(now: datetime) -> tuple[str, str]:
    hour = now.hour
    if 5 <= hour < 8:
        return "清晨", "窗外的光刚透进来，屋里还没开灯"
    if 8 <= hour < 11:
        return "上午", "日光照进来，屋里是亮的"
    if 11 <= hour < 13:
        return "中午", "正午的光，屋里很亮"
    if 13 <= hour < 17:
        return "下午", "午后的光斜进来"
    if 17 <= hour < 19:
        return "傍晚", "天开始暗，屋里开了灯"
    if 19 <= hour < 22:
        return "晚上", "只开了一盏落地灯"
    if 22 <= hour < 24:
        return "夜里", "屋里只剩一盏小灯"
    return "深夜", "屋里黑着，只有窗外一点光"


def distance_text(distance_cm: int) -> str:
    value = max(0, int(distance_cm))
    if value <= 5:
        return "贴着你"
    if value <= 120:
        return f"{value} 厘米"
    return f"约 {value / 100:.1f} 米"


def _step_text(level: float) -> str:
    if level <= 0.02:
        return "空了"
    if level < 0.97:
        return f"剩{max(1, min(9, int(round(level * 10))))}成"
    return ""


_DRINKABLE = ("可乐", "水", "饮料", "汤", "牛奶", "咖啡", "茶", "酒", "果汁", "汽水")


def _describe_prop(prop: Prop) -> str:
    bits: list[str] = []
    drinkable = any(word in prop.name for word in _DRINKABLE)
    if drinkable:
        if prop.temp and prop.temp != "常温":
            bits.append(prop.temp)
        if not any(word in prop.note for word in ("半", "空", "满")):
            step = _step_text(prop.level)
            if step:
                bits.append(step)
    if prop.note:
        bits.append(prop.note)
    if not bits:
        return prop.name
    return f"{prop.name}（{'，'.join(bits)}）"


def _describe_group(props: Iterable[Prop]) -> str:
    buckets: dict[tuple[str, str, float, str], list[Prop]] = {}
    for prop in props:
        key = (prop.name, prop.temp, round(prop.level, 2), prop.note)
        buckets.setdefault(key, []).append(prop)
    parts: list[str] = []
    for bucket in buckets.values():
        sample = bucket[0]
        text = _describe_prop(sample)
        if len(bucket) > 1:
            text = text.replace(sample.name, f"{sample.name} ×{len(bucket)}", 1)
        parts.append(text)
    return "、".join(parts)


def _group_props(props: Iterable[Prop]) -> list[str]:
    grouped: dict[str, list[Prop]] = {}
    for prop in props:
        grouped.setdefault(prop.holder, []).append(prop)

    lines: list[str] = []
    for holder in HOLDER_ORDER:
        items = grouped.get(holder)
        if not items:
            continue
        lines.append(
            f"{HOLDER_LABELS.get(holder, holder)}：{_describe_group(items)}"
        )
    return lines


def _affordances(state: PresenceState, user_text: str, label: str) -> list[str]:
    """给她一条“这一轮可以主动做什么”，不是替用户安排动作。"""

    if not state.user_place_known:
        return ["她可以先问你在哪、在忙什么；不要替他编位置、坐姿或手里拿着什么。"]

    if not state.together:
        return [
            f"她在{state.scene_place}，够不着你：先说她自己这边的事，"
            "或者问你要不要过去；不要写碰到你、递东西到你手里。"
        ]

    text = user_text or ""
    activity = state.activity or ""

    if any(key in text for key in ("渴", "喝", "可乐", "饮料", "水", "来一罐")):
        if any(p.name == "可乐" and p.holder == "fridge" for p in state.props):
            return ["她可以自己起身去冰箱拿一罐，先写开冰箱、拿出来的动作；给不给、怎么给，由她决定。"]
        if any(p.name == "可乐" and p.holder == "you" for p in state.props):
            return ["你手里那罐可乐还在；她可以就着这罐说话，不要凭空又变出一罐。"]
    if any(key in text for key in ("冷", "凉", "手凉", "脚凉", "冻", "僵")):
        return [f"{label}体寒：她可以先把你的手背贴到自己掌心，写清温度差；不用做很多事。"]
    if any(key in text for key in ("困", "睡", "累", "熬夜")):
        return ["她可以把沙发扶手上的毛毯抖开、递过去；动作轻一点，不用替他盖好。"]
    if any(key in text for key in ("饿", "吃", "饭", "汤")):
        return ["她可以把茶几上那半碗汤往你这边推一点，或先问一句饿不饿。"]
    if any(key in activity for key in ("读", "书", "写", "翻")):
        return ["她可以先按自己的节奏把手里的书翻一页，再抬头接你的话；不要一连做几件事。"]
    if any(p.holder in {"her", "bag"} for p in state.props):
        return ["她可以先低头弄一下自己手里的东西，再开口；动作只做一个。"]
    return ["她可以先开口，或把自己这边的东西挪一挪；这一轮最多一个动作。"]


def _render_compact(
    state: PresenceState,
    now: datetime,
    settings: RuntimeSettings,
    limit: int,
) -> str:
    """稳定轮只发变化和关键约束，避免每轮重复整份现场。"""

    period, _ = period_words(now)
    known = state.user_place_known
    together = known and state.together
    lines = [f"【现场】{now.strftime('%H:%M')} {period}。她在{state.scene_place}"]

    if together:
        lines.append(
            f"【你】你在{state.user_place_name}；离你{distance_text(state.distance_cm)}。"
        )
    elif known:
        lines.append(f"【你】你在{state.user_place_name}，不在这里；她够不到你。")
    else:
        lines.append("【你】没说在哪；她够不到你，不能碰你、不能递东西。")

    if state.activity:
        lines.append(f"【她】{state.activity}。")

    user_props = _describe_group(state.user_props())
    if user_props and known:
        lines.append("【你手里】" + user_props + "。")

    if together and state.contacts:
        lines.append("【碰着】" + "；".join(c.describe() for c in state.contacts) + "。")
    if state.pending:
        lines.append(f"【没做完】{state.pending}。")

    body = "\n".join(lines)
    wrapper_open, wrapper_close = "<physical_state>\n", "\n</physical_state>"
    if len(body) + len(wrapper_open) + len(wrapper_close) > limit:
        body = body[: max(0, limit - len(wrapper_open) - len(wrapper_close) - 1)] + "…"
    return wrapper_open + body + wrapper_close


def render_state(
    state: PresenceState,
    now: datetime,
    settings: RuntimeSettings,
    user_text: str = "",
    *,
    limit: int | None = None,
    compact: bool = False,
) -> str:
    label = settings.label
    period, default_light = period_words(now)
    light = settings.light_hint or default_light
    limit = limit or settings.max_chars

    if compact:
        return _render_compact(state, now, settings, limit)

    known = state.user_place_known
    together = known and state.together

    lines: list[str] = [
        f"【此刻】{now.strftime('%H:%M')}，{period}；{light}；室内{settings.indoor_temperature}。",
    ]

    if together:
        lines.extend(
            [
                f"【地方】{state.scene_place}"
                + (f"，{state.scene_detail}。" if state.scene_detail else "。"),
                f"【你】你在{state.user_place_name}；位置是你自己说的。"
                + (
                    f"姿势：{state.you_pose}。"
                    if state.user_pose_known and state.you_pose
                    else ""
                ),
                f"【{label}】{state.her_pose}，离你 {distance_text(state.distance_cm)}。",
            ]
        )
    elif known:
        lines.extend(
            [
                f"【地方】她在{state.scene_place}"
                + (f"，{state.scene_detail}。" if state.scene_detail else "。"),
                f"【你】你在{state.user_place_name}，不在这里。",
                f"【{label}】{state.her_pose}。",
                "【这一轮】你们不在一处：她够不到你，不能递东西、不能碰到你。"
                "可以说你这边的事，或者明确说你要过去找她。",
            ]
        )
    else:
        lines.extend(
            [
                f"【地方】她在{state.scene_place}"
                + (f"，{state.scene_detail}。" if state.scene_detail else "。"),
                f"【{label}】{state.her_pose}。",
                "【你】还没说你此刻在哪。她够不到你，不能碰你、不能递东西到你手里；"
                "不要替他安排位置、姿势、手里拿着什么；他没说就留白，或先问一句。",
            ]
        )

    if state.activity:
        lines.append(f"【{label}此刻在做】{state.activity}。")

    user_props = _describe_group(state.user_props())
    if user_props and known:
        lines.append("【你手里】" + user_props + "。")

    if together and state.contacts:
        lines.append(
            "【正碰着的地方】" + "；".join(c.describe() for c in state.contacts) + "。"
        )

    if state.pending:
        lines.append(f"【上一轮没做完的】{state.pending}。")

    if state.recent_actions:
        recent = "、".join(state.recent_actions[-1:])
        lines.append(f"【刚做过的动作，这一轮别重复】{recent}。")

    if state.facts:
        lines.append("【你们之间】" + "；".join(state.facts[:3]) + "。")

    hints = _affordances(state, user_text, label)
    if hints:
        lines.append("【她可以主动】" + " ".join(hints[:1]))

    body = "\n".join(lines)
    wrapper_open, wrapper_close = "<physical_state>\n", "\n</physical_state>"

    if len(body) + len(wrapper_open) + len(wrapper_close) > limit:
        if state.facts and len(body) > limit:
            body = "\n".join(line for line in lines if not line.startswith("【你们之间】"))
        if len(body) + len(wrapper_open) + len(wrapper_close) > limit:
            body = (
                body[: max(0, limit - len(wrapper_open) - len(wrapper_close) - 1)]
                + "…"
            )

    return wrapper_open + body + wrapper_close


def render_presence_log(state: PresenceState, now: datetime, settings: RuntimeSettings) -> str:
    """给日志看的一小段现场，不做调试参数堆砌。"""

    label = settings.label
    known = state.user_place_known
    together = known and state.together
    head = f"{now.strftime('%H:%M')} · {state.scene_place}"
    if state.scene_detail:
        head += f"（{state.scene_detail}）"
    lines = [head]
    if state.her_pose:
        line = f"{label}：{state.her_pose}"
        if together:
            line += f"，离你{distance_text(state.distance_cm)}"
        lines.append(line)
    if state.activity:
        lines.append(f"在做：{state.activity}")
    if known:
        line = f"你：在{state.user_place_name}"
        if state.user_pose_known and state.you_pose:
            line += f"，{state.you_pose}"
        lines.append(line)
        if not together:
            lines.append("距离：不在一处")
    else:
        lines.append("你：还没说在哪")
        lines.append("距离：还不知道")
    if together and state.contacts:
        lines.append("碰着：" + "；".join(c.describe() for c in state.contacts))
    if state.pending:
        lines.append(f"没做完：{state.pending}")
    return "\n".join(lines)


def render_protocol(
    settings: RuntimeSettings,
    together: bool = True,
    user_known: bool = True,
    compact: bool = False,
) -> str:
    label = settings.label

    if compact:
        rules = [
            "<physical_protocol>",
            f"她主导，1–2句，最多一个动作；动作写到部位、力度、温度。",
            "必须先有动作或台词，不能只输出 <phys> 状态块。",
            "别替用户安排位置、姿势或手里东西；他没说就问一句。",
        ]
        if not user_known:
            rules.append("不知道他在哪：不要写“手伸出来”“递给你”“往你手上”，先问一句。")
        elif not together:
            rules.append("你们不在一处：不写碰到他、递东西给他、“手伸出来”。")
        rules.append("只有他明确接过/喝了，才把东西记到他手里。")
        if settings.output_tag:
            rules.append("末尾一行 <phys>{...}</phys>，没变化写 {}。")
        rules.append("</physical_protocol>")
        return "\n".join(rules)

    scale = (
        "日常亲密（牵手、拥抱、靠肩、捂手、摸头）可以写；不写露骨内容。"
        if settings.intimacy_level == "日常"
        else "亲近（亲吻、长时间拥抱、贴着坐）可以写；不写露骨内容。"
    )

    rules = [
        "<physical_protocol>",
        f"她在主导：先做、先说，不等他下指令。一条 1–2 句，最多一个动作。",
        "必须先有动作或台词，不能只输出 <phys> 状态块。",
        "动作写到部位、力度、温度；拿东西先写从哪拿。",
        "不要替用户决定他在哪、在做什么、手里有什么；他没说就留白，或问一句。",
        "只有他明确接过/喝了，才把东西记到他手里；否则留在她手里，或写 pending。",
        "不写屏幕、手机、消息、语音、视频、表情包、宿舍、书桌、耳机。",
    ]

    if not user_known:
        rules.append(
            "他现在没说在哪：她够不到他，不要写“手伸出来”“递给你”“往你手上”，"
            "也不要写他坐在你旁边；先问一句。"
        )
    elif not together:
        rules.append(
            f"你们现在不在一处：她够不到他，不写碰到他、递东西给他、“手伸出来”、"
            f"{label}坐他旁边；只写她这边。"
        )
    else:
        rules.append(f"你们现在面对面：可以接触，但这一轮只做一件小事。")

    rules.append(f"尺度：{scale}")

    if settings.output_tag:
        rules.append(
            "每轮末尾单独一行，不解释；没变化写 <phys>{}</phys>。"
            "holder 用 you / her / bag / table / fridge 等："
        )
        rules.append(
            '<phys>{"props":[{"name":"可乐","holder":"her","level":0.9}],'
            '"distance":30,"pending":"把可乐递过去，他还没接"}</phys>'
        )

    rules.append("</physical_protocol>")
    return "\n".join(rules)


def render_card(state: PresenceState, now: datetime, settings: RuntimeSettings) -> str:
    label = settings.label
    period, default_light = period_words(now)
    light = settings.light_hint or default_light
    lines = [
        "🫧 现在的现场",
        f"时间：{now.strftime('%Y-%m-%d %H:%M')} · {period} · {light}",
    ]
    known = state.user_place_known
    together = known and state.together

    if together:
        lines.extend(
            [
                f"地方：{state.scene_place}"
                + (f"（{state.scene_detail}）" if state.scene_detail else ""),
                f"你：在{state.user_place_name}"
                + (f"，{state.you_pose}" if state.user_pose_known and state.you_pose else ""),
                f"{label}：{state.her_pose}",
                f"距离：{distance_text(state.distance_cm)}",
            ]
        )
    elif known:
        lines.extend(
            [
                f"{label}在：{state.scene_place}"
                + (f"（{state.scene_detail}）" if state.scene_detail else ""),
                f"你在：{state.user_place_name}",
                "状态：不在一处",
            ]
        )
    else:
        lines.extend(
            [
                f"{label}在：{state.scene_place}"
                + (f"（{state.scene_detail}）" if state.scene_detail else ""),
                "你：还没说在哪",
            ]
        )

    if state.activity:
        lines.append(f"{label}在做：{state.activity}")

    user_props = _describe_group(state.user_props())
    if user_props and known:
        lines.append("你手里：" + user_props)

    if together and state.contacts:
        lines.append("碰着：" + "；".join(c.describe() for c in state.contacts))
    if state.pending:
        lines.append(f"没做完：{state.pending}")
    return "\n".join(lines)
