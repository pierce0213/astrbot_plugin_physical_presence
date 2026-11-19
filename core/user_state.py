"""从用户自己的话里读“我在哪”。

原则：插件不替用户安排位置。只有他说了，才记录；没说就留白。
"""

from __future__ import annotations

import re

from .places import get_place

# 小句开头可以是“我”，也可以是逗号后省略主语的“在公司/在教室”。
_CLAUSE = r"(?:我(?:现在|此刻|这会儿|今天)?|(?<=[，,；;。]))"

_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (_CLAUSE + r"(?:在公司|在单位|在办公室|在上班|在工位|在开会)", "office", "公司"),
    (_CLAUSE + r"(?:在学校|在教室|在教学楼|在上课|在图书馆|在实验室)", "classroom", "学校"),
    (_CLAUSE + r"(?:在食堂|在餐厅|在吃饭|在打饭)", "canteen", "食堂"),
    (_CLAUSE + r"(?:在便利店|在超市|在商店|在买东西)", "convenience", "便利店"),
    (_CLAUSE + r"(?:在公园|在操场|在散步|在湖边|在跑步)", "park", "公园"),
    (_CLAUSE + r"(?:在公交|在地铁|在车上|在路上|在堵车|在打车)", "bus", "路上"),
    (_CLAUSE + r"(?:在街上|在街|在咖啡|在店里|在旧书街|在商场)", "street", "街上"),
    (
        _CLAUSE + r"(?:不在家|没在家|不在屋里|出门了|在外面|在外边|在楼下|在小区里)",
        "street",
        "外面",
    ),
    (
        _CLAUSE + r"(?:在家|在家里|在客厅|在卧室|在厨房|在院子|在书房|在沙发上|在床上|在宿舍|在寝室)",
        "home",
        "家里",
    ),
    (_CLAUSE + r"(?:回家了|到家了|回来了|刚到家)", "home", "家里"),
)

_LOCATION_RE = [(re.compile(pattern), key, label) for pattern, key, label in _PATTERNS]

_ACCEPT_WORDS = (
    "接过",
    "接住",
    "拿过来",
    "拿了",
    "握在手里",
    "端过来",
    "端着",
    "收下",
    "我拿着",
)
_DRINK_WORDS = ("喝了", "喝了一口", "喝掉", "灌了一口", "尝了", "喝了两口")
_POSE_WORDS = (
    "坐着",
    "躺着",
    "站着",
    "靠着",
    "蹲着",
    "趴着",
    "靠在",
    "坐在",
    "躺在",
    "站在",
)


def detect_user_pose(text: str | None) -> str | None:
    """用户自己说了姿势才记录，例如“我在家躺着”。"""

    if not isinstance(text, str) or not text.strip():
        return None
    for clause in re.split(r"[，,。；;！!？?\n]", text):
        clause = clause.strip()
        if "我" not in clause:
            continue
        if not any(word in clause for word in _POSE_WORDS):
            continue
        clause = re.sub(r"^我(?:现在|正|此刻|这会儿)?", "", clause).strip()
        for word in _POSE_WORDS:
            index = clause.find(word)
            if index >= 0:
                return clause[index:][:30] or None
        return None
    return None



def detect_user_location(text: str | None) -> tuple[str, str] | None:
    """返回 (地点 key, 说法)；用户没说自己的位置时返回 None。"""

    if not isinstance(text, str) or not text.strip():
        return None
    for pattern, key, label in _LOCATION_RE:
        if pattern.search(text):
            # 只接受注册表里有的地点，防止把奇怪说法塞进现场
            if get_place(key) is not None:
                return key, label
    return None


def user_accepts(text: str | None) -> bool:
    """用户是否明确说“我接过了/我拿着”。"""

    return isinstance(text, str) and any(word in text for word in _ACCEPT_WORDS)


def user_drinks(text: str | None) -> bool:
    return isinstance(text, str) and any(word in text for word in _DRINK_WORDS)


def apply_user_action(state, text: str | None) -> list[str]:
    """用户明确说“我接过了/我喝了”时，才回写他的动作。返回日志片段。"""

    notes: list[str] = []
    if not isinstance(text, str):
        return notes

    accepted = None
    if user_accepts(text):
        target = None
        for prop in state.props:
            if prop.holder in {"her", "lap"} and (
                prop.name in text or (state.pending and prop.name in state.pending)
            ):
                target = prop
                break
        if target is None and state.pending:
            target = next(
                (
                    p
                    for p in state.props
                    if p.holder in {"her", "lap"} and p.name in state.pending
                ),
                None,
            )
        if target is None:
            candidates = [
                p for p in state.props if p.holder in {"her", "lap"}
            ]
            if len(candidates) == 1:
                target = candidates[0]
        if target is not None:
            target.holder = "you"
            accepted = target
            state.pending = ""
            notes.append(f"用户接过了 {target.name}")

    if user_drinks(text):
        target = accepted
        if target is None:
            target = next(
                (p for p in state.props if p.holder == "you" and p.name in text),
                None,
            )
        if target is not None:
            target.level = round(max(0.05, target.level * 0.75), 2)
            notes.append(f"用户喝了 {target.name}")

    return notes


