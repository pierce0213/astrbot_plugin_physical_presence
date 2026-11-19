"""物理现场的数据结构与状态迁移。

一句话原则：每一轮对话结束后，"她手里有什么、你手里有什么、离多远、
哪里还碰着、上一轮什么动作没做完"都要能落到磁盘，下一轮原样接上。
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .constants import HOLDER_LABELS, normalize_holder

HOME_KEYS = {"home", "kitchen", "yard", "bedroom"}


def same_place(a: str, b: str) -> bool:
    """客厅/厨房/院子算同一个屋檐下；卧室是独立房间，不能隔墙碰到。"""

    if not a or not b:
        return False
    if a == b:
        return True
    if "bedroom" in {a, b}:
        return False
    return a in HOME_KEYS and b in HOME_KEYS


def _now() -> float:
    return time.time()


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _short(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    return text[:limit]


@dataclass
class Prop:
    """一件具体的东西。同一款可乐在冰箱里有两罐，就是两个 Prop。"""

    uid: str
    name: str
    holder: str = "table"
    temp: str = "常温"
    level: float = 1.0
    note: str = ""
    place: str = "home"
    updated_at: float = 0.0

    @property
    def holder_label(self) -> str:
        return HOLDER_LABELS.get(self.holder, self.holder)

    def describe(self) -> str:
        bits: list[str] = []
        if self.temp:
            bits.append(self.temp)
        has_amount_note = any(word in self.note for word in ("半", "空", "满"))
        if not has_amount_note:
            if self.level <= 0.02:
                bits.append("空了")
            elif self.level < 0.97:
                tenth = max(1, min(9, int(round(self.level * 10))))
                bits.append(f"剩{tenth}成")
        if self.note:
            bits.append(self.note)
        if not bits:
            return self.name
        return f"{self.name}（{'，'.join(bits)}）"

    def apply(self, patch: dict[str, Any], now: float) -> None:
        if "holder" in patch and patch["holder"]:
            self.holder = normalize_holder(patch["holder"], self.holder)
        if "temp" in patch and patch["temp"]:
            self.temp = _short(patch["temp"], 6)
        if "level" in patch and patch["level"] is not None:
            self.level = _clamp(patch["level"], 0.0, 1.0, self.level)
        if "note" in patch:
            self.note = _short(patch["note"], 18)
        self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Prop":
        return cls(
            uid=str(data.get("uid") or data.get("name") or "物品"),
            name=str(data.get("name") or data.get("uid") or "物品")[:12],
            holder=str(data.get("holder") or "table"),
            temp=str(data.get("temp") or "常温")[:6],
            level=_clamp(data.get("level", 1.0), 0.0, 1.0, 1.0),
            note=str(data.get("note") or "")[:18],
            place=str(data.get("place") or "home")[:16],
            updated_at=float(data.get("updated_at") or 0.0),
        )


@dataclass
class Contact:
    """一处正在发生的身体接触，例如"她的脚踝在你掌心里"。"""

    her: str
    you: str
    force: str = "轻轻搭着"
    note: str = ""
    since: float = 0.0

    def describe(self) -> str:
        base = f"她的{self.her}贴在你{self.you}（{self.force}"
        if self.note:
            base += f"，{self.note}"
        return base + "）"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Contact":
        return cls(
            her=_short(data.get("her") or "手", 8),
            you=_short(data.get("you") or "手背", 8),
            force=_short(data.get("force") or "轻轻搭着", 12),
            note=_short(data.get("note") or "", 18),
            since=float(data.get("since") or 0.0),
        )


@dataclass
class PresenceState:
    """一个会话/人格的完整物理现场。"""

    key: str
    place_key: str = "home"
    scene_place: str = "家里"
    scene_detail: str = "客厅，沙发和茶几之间"
    her_pose: str = "盘腿坐在地毯上，背靠着沙发"
    you_pose: str = ""
    user_place_key: str = ""
    user_place_name: str = ""
    user_place_known: bool = False
    user_pose_known: bool = False
    distance_cm: int = 40
    together: bool = False
    activity: str = ""
    outfit: str = ""
    life_block: str = ""
    pending: str = ""
    props: list[Prop] = field(default_factory=list)
    contacts: list[Contact] = field(default_factory=list)
    recent_actions: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    seeded_places: list[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    context_sig: str = ""

    # ---------- 物品 ----------

    def find_prop(self, name: str) -> Prop | None:
        hint = str(name or "").strip().lower()
        if not hint:
            return None
        candidates = [
            p
            for p in self.props
            if hint == p.uid.lower()
            or hint == p.name.lower()
            or hint in p.name.lower()
            or p.name.lower() in hint
        ]
        if not candidates:
            return None
        priority = {
            "you": 0,
            "her": 1,
            "table": 2,
            "dining": 3,
            "sofa": 4,
            "floor": 5,
            "bed": 6,
            "sink": 7,
            "kitchen": 8,
            "fridge": 9,
        }
        return min(candidates, key=lambda p: priority.get(p.holder, 20))

    def move_prop(
        self,
        name: str,
        holder: str,
        now: float,
        *,
        level: float | None = None,
        temp: str | None = None,
        note: str | None = None,
        place: str | None = None,
    ) -> Prop:
        prop = self.find_prop(name)
        target = normalize_holder(holder, "table")
        if prop is None:
            uid = _short(name, 12) or "物品"
            prop = Prop(
                uid=uid, name=uid, holder=target, place=place or self.place_key
            )
            self.props.append(prop)
        prop.holder = target
        prop.place = place or self.place_key
        prop.updated_at = now
        if level is not None:
            prop.level = _clamp(level, 0.0, 1.0, prop.level)
        if temp:
            prop.temp = _short(temp, 6)
        if note is not None:
            prop.note = _short(note, 18)
        return prop

    # ---------- 状态块 ----------

    def apply_patch(self, patch: dict[str, Any], now: float) -> list[str]:
        """应用模型输出的 <phys> 状态块，返回给日志看的变更摘要。"""

        if not isinstance(patch, dict) or not patch:
            return []
        notes: list[str] = []

        props = patch.get("props")
        if isinstance(props, list):
            seen_names: set[str] = set()
            for item in props:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("uid") or "").strip()
                if not name:
                    continue
                if name.lower() in seen_names:
                    continue
                seen_names.add(name.lower())
                holder = item.get("holder")
                if holder:
                    prop = self.move_prop(
                        name,
                        str(holder),
                        now,
                        level=item.get("level"),
                        temp=item.get("temp"),
                        note=item.get("note"),
                    )
                    notes.append(f"{prop.name}->{prop.holder_label}")
                else:
                    prop = self.find_prop(name)
                    if prop is None:
                        continue
                    prop.apply(item, now)
                    notes.append(f"{prop.name}={prop.describe()}")

        contacts = patch.get("contacts")
        if isinstance(contacts, list):
            next_contacts: list[Contact] = []
            for item in contacts:
                if not isinstance(item, dict):
                    continue
                her = str(item.get("her") or "").strip()
                if not her:
                    continue
                next_contacts.append(
                    Contact(
                        her=her[:8],
                        you=str(item.get("you") or "手背")[:8],
                        force=str(item.get("force") or "轻轻搭着")[:12],
                        note=str(item.get("note") or "")[:18],
                        since=now,
                    )
                )
            self.contacts = next_contacts
            notes.append(f"接触×{len(next_contacts)}")

        for item in patch.get("contact_add") or []:
            if not isinstance(item, dict):
                continue
            her = str(item.get("her") or "").strip()
            if not her:
                continue
            self.contacts.append(
                Contact(
                    her=her[:8],
                    you=str(item.get("you") or "手背")[:8],
                    force=str(item.get("force") or "轻轻搭着")[:12],
                    note=str(item.get("note") or "")[:18],
                    since=now,
                )
            )
            notes.append(f"+接触({her})")

        release = patch.get("release")
        if isinstance(release, list):
            for word in release:
                token = str(word or "").strip()
                if not token:
                    continue
                before = len(self.contacts)
                self.contacts = [
                    c for c in self.contacts if token not in c.her and token not in c.you
                ]
                if len(self.contacts) != before:
                    notes.append(f"-接触({token})")

        if patch.get("distance") is not None:
            self.distance_cm = int(_clamp(patch.get("distance"), 0, 500, self.distance_cm))
            notes.append(f"距离{self.distance_cm}cm")

        if patch.get("activity"):
            self.activity = _short(patch.get("activity"), 40)
            notes.append(f"活动={self.activity}")

        if "pending" in patch:
            self.pending = _short(patch.get("pending"), 120)
            if self.pending:
                notes.append("留了个没做完的动作")

        if patch.get("place"):
            self.scene_place = _short(patch.get("place"), 20)

        return notes

    # ---------- 时间推移 ----------

    def tick(self, now: float, contact_stale_minutes: int, cold_fade_minutes: int) -> None:
        if contact_stale_minutes > 0:
            self.contacts = [
                c
                for c in self.contacts
                if now - (c.since or now) <= contact_stale_minutes * 60
            ]
        for prop in self.props:
            if prop.updated_at <= 0:
                prop.updated_at = now
                continue
            if (
                cold_fade_minutes > 0
                and prop.temp == "冰"
                and now - prop.updated_at > cold_fade_minutes * 60
            ):
                prop.temp = "常温"
                prop.note = (
                    prop.note.replace("罐身挂着水珠", "")
                    .replace("挂着水珠", "")
                    .replace("水珠", "")
                    .strip("，、 ")
                )

    def note_action(self, action: str, limit: int = 5) -> None:
        text = _short(action, 20)
        if not text:
            return
        if text in self.recent_actions:
            self.recent_actions.remove(text)
        self.recent_actions.append(text)
        if limit > 0:
            self.recent_actions = self.recent_actions[-limit:]

    # ---------- 地点 ----------

    def set_user_place(self, place_key: str, name: str) -> None:
        """用户自己说了他在哪。插件不替他猜位置，只记录他说过的。"""

        self.user_place_key = str(place_key or "")[:16]
        self.user_place_name = _short(name, 20)
        self.user_place_known = bool(self.user_place_key)
        self.together = bool(
            self.user_place_known
            and self.user_place_key
            and same_place(self.user_place_key, self.place_key)
        )
        if not self.together:
            self.contacts = []
            self.pending = ""
        self.you_pose = ""
        self.user_pose_known = False

    def forget_user_place(self) -> None:
        self.user_place_key = ""
        self.user_place_name = ""
        self.user_place_known = False
        self.user_pose_known = False
        self.you_pose = ""
        self.together = False

    def her_props(self) -> list[Prop]:
        """她此刻手边/身上/随身包里的东西。"""

        return [
            p
            for p in self.props
            if p.holder in {"her", "bag"}
            or (p.place == self.place_key and p.holder != "you")
        ]

    def user_props(self) -> list[Prop]:
        """用户明确拿在手里的东西；没说过就是没有。"""

        return [p for p in self.props if p.holder == "you"]

    def visible_props(self) -> list[Prop]:
        """兼容旧接口：在一起时看得到双方，分开时只看她那边。"""

        if self.together:
            return self.her_props() + self.user_props()
        return self.her_props()

    def enter_place(
        self,
        preset,
        now: float,
        *,
        together: bool = False,
        user_preset=None,
    ) -> bool:
        """她进入一个新地点。她在哪由日程决定；你在哪只由你说过的话决定。"""

        changed = False

        if self.place_key != preset.key:
            self.place_key = preset.key
            self.scene_place = preset.name
            self.scene_detail = preset.detail
            self.her_pose = preset.her_pose
            self.contacts = []
            self.pending = ""
            changed = True
            if preset.key not in self.seeded_places:
                self.props.extend(
                    props_from_config(list(preset.props), now, place=preset.key)
                )
                self.seeded_places.append(preset.key)
            for prop in self.props:
                if prop.holder in {"her", "bag"}:
                    prop.place = preset.key

        if together:
            if not self.together:
                self.contacts = []
                self.pending = ""
            self.together = True
            if not self.user_place_known or not same_place(
                self.user_place_key, preset.key
            ):
                self.user_place_key = preset.key
                self.user_place_name = preset.name
            self.user_place_known = True
            self.distance_cm = int(preset.distance_cm)
        else:
            self.together = False
            if user_preset is not None:
                if (
                    self.user_place_key != user_preset.key
                    or self.user_place_name != user_preset.name
                ):
                    changed = True
                self.user_place_key = user_preset.key
                self.user_place_name = user_preset.name
                self.user_place_known = True
                if user_preset.key not in self.seeded_places:
                    self.props.extend(
                        props_from_config(
                            list(user_preset.props), now, place=user_preset.key
                        )
                    )
                    self.seeded_places.append(user_preset.key)

        self.updated_at = now
        return changed

    def set_activity(self, activity: str) -> None:
        self.activity = _short(activity, 40)

    # ---------- 序列化 ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "place_key": self.place_key,
            "scene_place": self.scene_place,
            "scene_detail": self.scene_detail,
            "her_pose": self.her_pose,
            "you_pose": self.you_pose,
            "user_place_key": self.user_place_key,
            "user_place_name": self.user_place_name,
            "user_place_known": self.user_place_known,
            "user_pose_known": self.user_pose_known,
            "distance_cm": self.distance_cm,
            "together": self.together,
            "activity": self.activity,
            "outfit": self.outfit,
            "life_block": self.life_block,
            "pending": self.pending,
            "props": [p.to_dict() for p in self.props],
            "contacts": [c.to_dict() for c in self.contacts],
            "recent_actions": list(self.recent_actions),
            "facts": list(self.facts),
            "seeded_places": list(self.seeded_places),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "context_sig": self.context_sig,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], key: str) -> "PresenceState":
        user_known = bool(data.get("user_place_known", False))
        state = cls(
            key=key,
            place_key=str(data.get("place_key") or "home")[:16],
            scene_place=str(data.get("scene_place") or "家里")[:20],
            scene_detail=str(data.get("scene_detail") or "")[:30],
            her_pose=str(data.get("her_pose") or "")[:60],
            you_pose=str(data.get("you_pose") or "")[:60],
            user_place_key=str(data.get("user_place_key") or "")[:16],
            user_place_name=str(data.get("user_place_name") or "")[:20],
            user_place_known=user_known,
            user_pose_known=bool(data.get("user_pose_known", False)),
            distance_cm=int(_clamp(data.get("distance_cm"), 0, 500, 40)),
            together=bool(data.get("together", False)) and user_known,
            activity=str(data.get("activity") or "")[:40],
            outfit=str(data.get("outfit") or "")[:260],
            life_block=str(data.get("life_block") or "")[:24],
            pending=str(data.get("pending") or "")[:120],
            recent_actions=[
                str(a)[:60] for a in (data.get("recent_actions") or []) if str(a).strip()
            ][-8:],
            facts=[str(f)[:80] for f in (data.get("facts") or []) if str(f).strip()],
            seeded_places=[
                str(p)[:16] for p in (data.get("seeded_places") or []) if str(p).strip()
            ],
            created_at=float(data.get("created_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
            context_sig=str(data.get("context_sig") or "")[:32],
        )
        state.props = [
            Prop.from_dict(item)
            for item in (data.get("props") or [])
            if isinstance(item, dict)
        ]
        state.contacts = [
            Contact.from_dict(item)
            for item in (data.get("contacts") or [])
            if isinstance(item, dict)
        ]
        return state

    # ---------- 构造 ----------

    @classmethod
    def fresh(
        cls,
        key: str,
        *,
        place: str,
        detail: str,
        her_pose: str,
        distance_cm: int,
        facts: list[str],
        props: list[Prop],
        now: float,
        place_key: str = "home",
        together: bool = False,
    ) -> "PresenceState":
        state = cls(
            key=key,
            place_key=place_key,
            scene_place=place,
            scene_detail=detail,
            her_pose=her_pose,
            you_pose="",
            distance_cm=int(_clamp(distance_cm, 0, 500, 40)),
            together=False,
            facts=list(facts),
            props=list(props),
            seeded_places=[place_key],
            created_at=now,
            updated_at=now,
        )
        return state


def props_from_config(
    lines: list[str], now: float | None = None, place: str = "home"
) -> list[Prop]:
    """把配置里的 "可乐 x3 | 冰箱 | 冰 | 罐身挂着水珠" 解析成具体物品。"""

    now = now if now is not None else time.time()
    props: list[Prop] = []
    for line in lines or []:
        parts = [part.strip() for part in str(line).split("|")]
        head = parts[0] if parts else ""
        if not head:
            continue
        count = 1
        match = re.search(r"(?:x|×|X)\s*(\d+)\s*$", head)
        if match:
            count = max(1, min(20, int(match.group(1))))
            name = head[: match.start()].strip()
        else:
            name = head
        if not name:
            continue
        holder = normalize_holder(parts[1] if len(parts) > 1 else "", "table")
        temp = parts[2] if len(parts) > 2 and parts[2] else "常温"
        note = parts[3] if len(parts) > 3 else ""
        level = 1.0
        for hint, value in (
            ("空", 0.0),
            ("剩一点", 0.1),
            ("剩半", 0.5),
            ("半碗", 0.5),
            ("半罐", 0.5),
        ):
            if hint in note or hint in name:
                level = value
                break
        for index in range(count):
            uid = f"{name}{index + 1}" if count > 1 else name
            props.append(
                Prop(
                    uid=uid,
                    name=name,
                    holder=holder,
                    temp=temp,
                    level=level,
                    note=note,
                    place=place,
                    updated_at=now,
                )
            )
    return props
