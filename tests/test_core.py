"""不依赖 AstrBot 的本地测试：跑状态机、解析、去屏幕化、场景切换。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR))

from core.context import build_injection  # noqa: E402
from core.guard import de_mediate, ensure_action, strip_away_contact  # noqa: E402
from core.life import build_plan  # noqa: E402
from core.models import PresenceState, props_from_config  # noqa: E402
from core.parser import extract_state_block, heuristic_patch  # noqa: E402
from core.pipeline import process_output  # noqa: E402
from core.places import get_place, match_place  # noqa: E402
from core.render import render_protocol, render_state  # noqa: E402
from core.settings import RuntimeSettings  # noqa: E402
from core.user_state import (  # noqa: E402
    apply_user_action,
    detect_user_location,
    detect_user_pose,
    user_accepts,
)
from core.virtual_life import VirtualLifeReader  # noqa: E402

NOW = datetime(2026, 11, 18, 19, 15)


def make_state() -> PresenceState:
    settings = RuntimeSettings()
    props = props_from_config(settings.initial_props, NOW.timestamp(), "home")
    state = PresenceState.fresh(
        key="test",
        place_key="home",
        place="家里",
        detail="客厅，沙发和茶几之间",
        her_pose=settings.her_pose,
        distance_cm=40,
        facts=settings.facts,
        props=props,
        now=NOW.timestamp(),
    )
    state.set_user_place("home", "家里")
    return state


class UserStateTest(unittest.TestCase):
    def test_detect_user_location(self) -> None:
        self.assertEqual(detect_user_location("我不在家，在公司加班")[0], "office")
        self.assertEqual(detect_user_location("我在教室，晚点回")[0], "classroom")
        self.assertEqual(detect_user_location("我刚到家")[0], "home")
        self.assertIsNone(detect_user_location("今天好累"))
        self.assertEqual(detect_user_pose("我在家躺着"), "躺着")

    def test_pose_shows_only_when_user_said_it(self) -> None:
        state = make_state()
        state.set_user_place("home", "家里")
        state.you_pose = "躺着"
        state.user_pose_known = True
        rendered = render_state(state, NOW, RuntimeSettings())
        self.assertIn("姿势：躺着", rendered)

    def test_unknown_user_has_no_phantom_pose(self) -> None:
        state = PresenceState.fresh(
            key="unknown",
            place_key="home",
            place="家里",
            detail="客厅",
            her_pose="盘腿坐在地毯上",
            distance_cm=40,
            facts=["测试事实"],
            props=props_from_config(RuntimeSettings().initial_props, NOW.timestamp(), "home"),
            now=NOW.timestamp(),
        )
        self.assertFalse(state.user_place_known)
        self.assertFalse(state.together)
        rendered = render_state(state, NOW, RuntimeSettings())
        self.assertIn("还没说你此刻在哪", rendered)
        self.assertNotIn("【你】你在", rendered)
        self.assertNotIn("【你手里】", rendered)
        self.assertNotIn("坐在沙发上", rendered)

    def test_user_says_not_home(self) -> None:
        state = make_state()
        state.set_user_place("office", "公司")
        self.assertFalse(state.together)
        rendered = render_state(state, NOW, RuntimeSettings())
        self.assertIn("你在公司", rendered)
        self.assertNotIn("正碰着的地方", rendered)

    def test_home_and_kitchen_are_same_house(self) -> None:
        state = make_state()
        state.enter_place(get_place("kitchen"), NOW.timestamp(), together=True)
        self.assertTrue(state.together)
        self.assertEqual(state.user_place_key, "home")
        self.assertIn("你在家里", render_state(state, NOW, RuntimeSettings()))

    def test_she_leads_and_short_protocol(self) -> None:
        protocol = render_protocol(RuntimeSettings(), together=True)
        self.assertIn("她在主导", protocol)
        self.assertIn("1–2 句", protocol)
        self.assertLess(len(protocol), 620)

    def test_stable_turn_is_compact(self) -> None:
        state = make_state()
        full = build_injection(state, NOW, RuntimeSettings(), "我在家")
        compact = build_injection(state, NOW, RuntimeSettings(), "我在家")
        self.assertLess(len(compact), len(full) * 0.65)
        self.assertIn("【现场】", compact)
        self.assertIn("她主导", compact)
        self.assertNotIn("【你们之间】", compact)

    def test_state_change_returns_full(self) -> None:
        state = make_state()
        build_injection(state, NOW, RuntimeSettings(), "我在家")
        state.set_user_place("office", "公司")
        changed = build_injection(state, NOW, RuntimeSettings(), "我在公司")
        self.assertIn("【地方】", changed)
        self.assertIn("不在这里", changed)

    def test_context_signature_survives_restart(self) -> None:
        state = make_state()
        build_injection(state, NOW, RuntimeSettings(), "我在家")
        restored = PresenceState.from_dict(state.to_dict(), state.key)
        self.assertEqual(restored.context_sig, state.context_sig)
        self.assertTrue(restored.context_sig)

    def test_away_touch_is_stripped(self) -> None:
        text = "（拧开小罐，往你手背挤了一小团，用指腹慢慢抹开）\n手伸出来。"
        cleaned, hits = strip_away_contact(text)
        self.assertNotIn("你手背", cleaned)
        self.assertNotIn("手伸出来", cleaned)
        self.assertIn("你在哪儿", cleaned)
        self.assertTrue(hits)

    def test_user_accepts_coke(self) -> None:
        state = make_state()
        self.assertTrue(user_accepts("我接过来喝了"))
        state.pending = "把可乐递过去，他还没接"
        state.move_prop("可乐", "her", NOW.timestamp())
        before = state.find_prop("可乐").level
        notes = apply_user_action(state, "我接过来，喝了一口")
        prop = state.find_prop("可乐")
        self.assertEqual(prop.holder, "you")
        self.assertLess(prop.level, before)
        self.assertEqual(state.pending, "")
        self.assertTrue(notes)


class PropFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = make_state()
        self.settings = RuntimeSettings()

    def test_hand_over_coke(self) -> None:
        raw = (
            "（起身走到冰箱前，拉开门，拿出一罐可乐，罐身的水珠沾了一手，"
            "走回来递到你手边）\n给。冰的，慢点喝。\n"
            '<phys>{"props":[{"name":"可乐","holder":"you"}],"distance":30,'
            '"activity":"递可乐","pending":""}</phys>'
        )
        result = process_output(raw, self.state, NOW, self.settings)
        self.assertNotIn("<phys>", result.text)
        self.assertIn("给", result.text)
        prop = self.state.find_prop("可乐")
        self.assertEqual(prop.holder, "you")
        self.assertEqual(self.state.distance_cm, 30)
        rendered = render_state(self.state, NOW, self.settings)
        self.assertIn("你手里", rendered)
        self.assertIn("罐身挂着水珠", rendered)

    def test_drink_then_put_down(self) -> None:
        self.state.move_prop("可乐", "you", NOW.timestamp())
        raw = (
            "（看你仰头喝了一口，伸手替你把罐子扶稳）\n慢点。\n"
            '<phys>{"props":[{"name":"可乐","level":0.7}]}</phys>'
        )
        process_output(raw, self.state, NOW, self.settings)
        prop = self.state.find_prop("可乐")
        self.assertEqual(prop.holder, "you")
        self.assertAlmostEqual(prop.level, 0.7, places=2)

        raw2 = (
            "（等你喝完，把空罐接过去，放在茶几上）\n放这儿了。\n"
            '<phys>{"props":[{"name":"可乐","holder":"table","level":0.0,'
            '"note":"空了"}]}</phys>'
        )
        process_output(raw2, self.state, NOW, self.settings)
        prop = self.state.find_prop("可乐")
        self.assertEqual(prop.holder, "table")
        self.assertIn("空了", prop.describe())

    def test_heuristic_transfer(self) -> None:
        raw = "（从茶几上端起汤碗，递到你手里）\n还温着。"
        guessed = heuristic_patch(raw, self.state)
        self.state.apply_patch(guessed, NOW.timestamp())
        prop = self.state.find_prop("汤碗")
        self.assertEqual(prop.holder, "you")

    def test_release_contact(self) -> None:
        from core.models import Contact

        self.state.contacts = [Contact(her="手", you="脸侧", force="轻搭", since=0)]
        self.state.apply_patch({"release": ["手"]}, NOW.timestamp())
        self.assertEqual(self.state.contacts, [])


class GuardTest(unittest.TestCase):
    def test_rewrite_injection(self) -> None:
        text = (
            "<character_state>\n时间：2026-11-18 19:15\n"
            "当前活动：和哥哥视频吃晚饭\n地点：宿舍\n状态：social\n"
            "</character_state>"
        )
        cleaned, changed, _ = de_mediate(text)
        self.assertTrue(changed)
        self.assertNotIn("视频", cleaned)
        self.assertNotIn("宿舍", cleaned)
        self.assertIn("一起吃晚饭", cleaned)
        self.assertIn("家里", cleaned)

    def test_drop_screen_sentence(self) -> None:
        text = "（把手机往旁边推，屏幕暗下去）\n本来就是想把声音送给你呀。"
        cleaned, changed, hits = de_mediate(text)
        self.assertTrue(changed)
        self.assertNotIn("手机", cleaned)
        self.assertNotIn("屏幕", cleaned)
        self.assertIn("声音送给你", cleaned)
        self.assertTrue(hits)

    def test_ensure_action(self) -> None:
        state = make_state()
        text = ensure_action("嗯。\n那就捂着吧。", state, "她", [])
        self.assertTrue(text.startswith("（"))
        self.assertIn("那就捂着吧", text)

    def test_extract_invalid_block(self) -> None:
        raw = "给。\n<phys>{不是json}</phys>"
        clean, patch, found = extract_state_block(raw)
        self.assertTrue(found)
        self.assertEqual(patch, {})
        self.assertNotIn("phys", clean)


class SceneTest(unittest.TestCase):
    def test_switch_place_hides_home_props(self) -> None:
        state = make_state()
        classroom = get_place("classroom")
        state.enter_place(classroom, NOW.timestamp(), together=True)
        rendered = render_state(state, NOW, RuntimeSettings())
        self.assertIn("教室", rendered)
        self.assertIn("课本", rendered)
        self.assertNotIn("可乐 ×3", rendered)

    def test_carried_prop_follows(self) -> None:
        state = make_state()
        state.move_prop("可乐", "you", NOW.timestamp())
        state.enter_place(get_place("classroom"), NOW.timestamp(), together=True)
        rendered = render_state(state, NOW, RuntimeSettings())
        self.assertIn("【你手里】可乐", rendered)

    def test_apart(self) -> None:
        state = make_state()
        from core.models import Contact

        state.contacts = [Contact(her="脚", you="掌心", force="握着")]
        state.enter_place(
            get_place("classroom"),
            NOW.timestamp(),
            together=False,
            user_preset=get_place("home"),
        )
        self.assertFalse(state.together)
        self.assertEqual(state.contacts, [])
        rendered = render_state(state, NOW, RuntimeSettings())
        self.assertIn("不在这里", rendered)
        self.assertIn("你在家里", rendered)
        protocol = render_protocol(RuntimeSettings(), together=False)
        self.assertIn("不在一处", protocol)
        self.assertIn("不写碰到", protocol)


class LifeTest(unittest.TestCase):
    def test_builtin_student_plan(self) -> None:
        plan = build_plan("学生", "together")
        block = plan.block_at(NOW)
        self.assertIsNotNone(block)
        self.assertEqual(block.place_key, "home")
        self.assertTrue(block.with_user)

    def test_separate_mode(self) -> None:
        plan = build_plan("学生", "separate")
        block = plan.block_at(datetime(2026, 11, 18, 10, 0))
        self.assertEqual(block.place_key, "classroom")
        self.assertFalse(block.with_user)

    def test_place_matching(self) -> None:
        self.assertEqual(match_place("教学楼 302").key, "classroom")
        self.assertEqual(match_place("第二食堂").key, "canteen")
        self.assertEqual(match_place("宿舍书桌").key, "home")
        self.assertEqual(match_place("公交 27 路").key, "bus")
        self.assertEqual(match_place("旧书街区").key, "street")

    def test_virtual_life_reader(self) -> None:
        plan = {
            "date": "2026-11-18",
            "persona_id": "莉莉",
            "theme": "探索日",
            "mood": "随性",
            "outfit": {
                "summary": "白衬衫配深蓝背心",
                "items": [
                    {"category": "top", "name": "白衬衫"},
                    {"category": "underwear", "name": "白色打底"},
                    {"category": "shoes", "name": "短靴"},
                ],
            },
            "timeline": [
                {
                    "start": "18:40",
                    "end": "19:20",
                    "activity": "和哥哥视频吃晚饭",
                    "location": "宿舍",
                },
                {
                    "start": "19:20",
                    "end": "20:30",
                    "activity": "阅读与写点小散文",
                    "location": "宿舍书桌",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "plans.json").write_text(
                json.dumps({"plans": {"2026-11-18::莉莉": plan}}, ensure_ascii=False),
                encoding="utf-8",
            )
            reader = VirtualLifeReader(Path(tmp))
            found = reader.find_plan("2026-11-18", "阅读与写点小散文", "")
            self.assertIsNotNone(found)
            block = reader.block_at(found, datetime(2026, 11, 18, 19, 30))
            self.assertEqual(block["activity"], "阅读与写点小散文")
            outfit = reader.outfit_text(found)
            self.assertIn("白衬衫", outfit)
            self.assertNotIn("打底", outfit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
