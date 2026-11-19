"""无框架演练：把"递可乐→喝一口→放茶几→她手凉"整条链路跑一遍。"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR))

from core.life import build_plan  # noqa: E402
from core.models import PresenceState, props_from_config  # noqa: E402
from core.context import build_injection  # noqa: E402
from core.pipeline import process_output  # noqa: E402
from core.places import get_place  # noqa: E402
from core.render import render_card, render_state  # noqa: E402
from core.settings import RuntimeSettings  # noqa: E402
from core.user_state import apply_user_action, detect_user_location  # noqa: E402

NOW = datetime(2026, 11, 18, 19, 15)


def new_state(settings: RuntimeSettings) -> PresenceState:
    return PresenceState.fresh(
        key="demo",
        place_key="home",
        place="家里",
        detail="客厅，沙发和茶几之间",
        her_pose=settings.her_pose,
        distance_cm=40,
        facts=settings.facts,
        props=props_from_config(settings.initial_props, NOW.timestamp(), "home"),
        now=NOW.timestamp(),
    )


def user_says(state: PresenceState, text: str) -> None:
    loc = detect_user_location(text)
    if loc:
        state.set_user_place(*loc)
        print(f"\n[用户] {text} -> 你在{loc[1]}")
    for note in apply_user_action(state, text):
        print(f"[用户动作] {note}")


def turn(state: PresenceState, settings: RuntimeSettings, title: str, raw: str) -> None:
    result = process_output(raw, state, NOW, settings)
    print(f"\n===== {title} =====")
    print(result.text)
    if result.notes:
        print(f"[回写] {'，'.join(result.notes)}")
    if result.hits:
        print(f"[过滤] {'，'.join(str(h)[:10] for h in result.hits)}")


def main() -> None:
    settings = RuntimeSettings()
    state = new_state(settings)

    print("========== 第一轮注入（她在家，你还没说你在哪） ==========")
    print(render_state(state, NOW, settings))

    user_says(state, "我在家，有点渴")
    turn(
        state,
        settings,
        "她递可乐（先放在你手边，还没接）",
        "（起身走到冰箱前，拉开门，拿出一罐可乐，罐身的水珠沾了一手，"
        "走回来递到你手边）\n给。冰的，慢点喝。\n"
        '<phys>{"props":[{"name":"可乐","holder":"her"}],"distance":30,'
        '"activity":"递可乐","pending":"把可乐递过去，他还没接"}</phys>',
    )

    user_says(state, "我接过来，喝了一口")
    turn(
        state,
        settings,
        "你接过可乐",
        "（看你仰头喝了一口，伸手替你把罐子扶稳，指尖碰到你的手背）\n"
        "慢点，别呛着。\n"
        '<phys>{"props":[{"name":"可乐","holder":"you","level":0.7}],'
        '"contacts":[{"her":"指尖","you":"手背","force":"轻轻碰着"}],'
        '"distance":25}</phys>',
    )

    turn(
        state,
        settings,
        "用户：你手怎么这么凉",
        "（把手往袖子里缩了缩，又伸过来贴在你手背上）\n"
        "我体寒你又不是不知道。\n"
        '<phys>{"contacts":[{"her":"手心","you":"手背","force":"贴着"}],'
        '"pending":"她的手还贴在你手背上"}</phys>',
    )

    turn(
        state,
        settings,
        "用户：放桌上吧，我去洗个手",
        "（接过你手里的罐子，搁在茶几边上，罐底留下一圈水印）\n"
        "去吧，我给你留着。\n"
        '<phys>{"props":[{"name":"可乐","holder":"table","level":0.7}],'
        '"release":["手背"],"pending":""}</phys>',
    )

    print("\n========== 此刻的现场卡 ==========")
    print(render_card(state, NOW, settings))

    print("\n========== 第二天上午 10:00，她按自己的日程去教室；你也说在教室 ==========")
    plan = build_plan("学生", "separate")
    block = plan.block_at(datetime(2026, 11, 18, 10, 0))
    print(f"日程：{block.start}-{block.end} {block.place_key} · {block.activity}")
    state.set_user_place("classroom", "学校")
    state.enter_place(get_place(block.place_key), NOW.timestamp(), together=True)
    state.activity = block.activity
    injection = build_injection(state, NOW, settings, "今天上什么课")
    print(injection.split("\n\n")[0])

    print("\n========== 同一时刻，你说你在公司 ==========")
    state.set_user_place("office", "公司")
    print(render_state(state, datetime(2026, 11, 18, 10, 0), settings))

    print("\n\n[协议片段]")
    print(build_injection(state, NOW, settings).split("\n\n")[1][:600])


if __name__ == "__main__":
    main()
