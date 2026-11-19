"""回复的后处理：去屏幕化、补动作、拦露骨内容。

这一层是"她还在屏幕上"的最后一道保险：
虚拟人生注入的日程、模型自己写出来的台词，只要出现中介词，
要么换成面对面说法，要么整句删掉。
"""

from __future__ import annotations

import re
import zlib

from .constants import EXPLICIT_WORDS, MEDIATION_WORDS, SOFT_REPLACEMENTS
from .models import PresenceState
from .parser import ACTION_RE

# 一段话里区分"（）动作"和"台词"，避免动作和台词一起被删
TOKEN_RE = re.compile(r"[（(][^（）()]*[）)]|[^（(]+")
SENTENCE_RE = re.compile(r"(?<=[。！？!?；;])")
_AWAY_PAREN = re.compile(r"[（(][^（）()]*[）)]")
_AWAY_BODY = re.compile(
    r"往你|向你|到你|碰你|牵你|抱你|搂你|摸你|贴着你|靠着你|"
    r"你(?:的)?(?:手|脸|头|肩|腰|腿|脚|背|嘴|脖子|手腕|掌心|手背)"
)


def _drop_bad(text: str, banned: list[str]) -> tuple[str, list[str]]:
    dropped: set[str] = set()
    out_lines: list[str] = []

    for line in text.split("\n"):
        if not line.strip():
            out_lines.append("")
            continue
        kept_line: list[str] = []
        for token in TOKEN_RE.findall(line):
            if not token:
                continue
            low = token.lower()
            hit = next((word for word in banned if word.lower() in low), None)
            if hit:
                dropped.add(hit)
                continue
            # 台词部分按句切，只丢有问题的那一句
            for sentence in SENTENCE_RE.split(token):
                if not sentence:
                    continue
                sentence_low = sentence.lower()
                bad = next(
                    (word for word in banned if word.lower() in sentence_low), None
                )
                if bad:
                    dropped.add(bad)
                    continue
                kept_line.append(sentence)
        merged = "".join(kept_line).strip()
        if merged:
            out_lines.append(merged)

    result = "\n".join(out_lines)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result, sorted(dropped)


def de_mediate(text: str, extra_words: list[str] | tuple[str, ...] = ()) -> tuple[str, bool, list[str]]:
    """去掉"隔着屏幕"的味道。

    先做软替换（宿舍→家里、视频→见面/一起），再把仍然含中介词的句子删掉。
    返回 (文本, 是否改动, 命中的词/规则)。
    """

    if not isinstance(text, str) or not text.strip():
        return text or "", False, []

    hits: list[str] = []
    current = text
    for pattern, replacement in SOFT_REPLACEMENTS:
        updated, count = re.subn(pattern, replacement, current)
        if count:
            current = updated
            hits.append(pattern)

    banned = list(MEDIATION_WORDS) + [str(w) for w in extra_words if str(w).strip()]
    current, dropped = _drop_bad(current, banned)
    if dropped:
        hits.extend(dropped)
    return current, bool(hits), hits


def has_action(text: str) -> bool:
    return bool(ACTION_RE.search(text or ""))


def _candidates(state: PresenceState, label: str) -> list[str]:
    candidates: list[str] = []

    if not state.user_place_known:
        return [
            "（抬头看了眼门口，又低头做自己的事）",
            "（把手里的东西放下，偏头想了想）",
            "（往窗外看了一眼，收回视线）",
            "（轻轻呼了口气，坐直一点）",
        ]

    if not state.together:
        return [
            "（把手里的书合上，抬头看向门口）",
            "（低头看了眼手机上的时间，又收起来）",
            "（把杯子往桌角挪了挪，继续做自己的事）",
            "（偏头看向窗外，手指在桌沿轻轻敲了两下）",
        ]

    for contact in state.contacts[:2]:
        candidates.append(f"（{label}的{contact.her}在你{contact.you}上轻轻动了一下）")

    in_your_hand = [p for p in state.props if p.holder == "you" and p.name]
    if in_your_hand:
        candidates.append(f"（看了一眼你手里那{in_your_hand[0].name}）")

    in_her_hand = [p for p in state.props if p.holder == "her" and p.name]
    if in_her_hand:
        candidates.append(f"（把手里那{in_her_hand[0].name}往你手边递了递）")

    if state.distance_cm > 80:
        candidates.append("（起身走过来，站到你面前）")

    candidates.extend(
        [
            "（把袖口往上挽了挽，坐直一点）",
            "（偏头看你，手指在膝盖上轻轻敲了两下）",
            "（伸手把你面前的碗往旁边挪了挪）",
            "（抬眼看向你，肩膀松下来一点）",
            "（把毯子往你那边拉了拉，膝盖碰到你的腿）",
        ]
    )
    return candidates


def ensure_action(
    text: str,
    state: PresenceState,
    label: str = "她",
    recent: list[str] | None = None,
) -> str:
    """一条回复里没有任何（）动作时，补一个和现场对得上的小动作。

    不是随便加一句"她笑了"，而是从当前接触、手里的东西、距离里长出来的。
    """

    text = (text or "").strip()
    if has_action(text):
        return text

    pool = _candidates(state, label)
    recent = recent or []
    unused = [item for item in pool if item not in recent]
    if not unused:
        unused = pool
    if not unused:
        return text
    index = zlib.crc32(text.encode("utf-8")) % len(unused)
    action = unused[index]
    if not text:
        return action
    # 动作在前、台词在后，接近参考图二的节奏
    return f"{action}\n{text}"


def strip_away_contact(
    text: str, user_known: bool = False
) -> tuple[str, list[str]]:
    """不在一处时，把她“碰到你/递到你手里”的话改成她这边的事。"""

    if not text:
        return text, []

    hits: list[str] = []

    def _replace_action(match: re.Match[str]) -> str:
        block = match.group(0)
        if not _AWAY_BODY.search(block):
            return block
        hits.append(block[:12])
        return "（她收回手，没碰到你）"

    text = _AWAY_PAREN.sub(_replace_action, text)

    if "手伸出来" in text:
        hits.append("手伸出来")
        text = text.replace("手伸出来", "你还没告诉我你在哪儿")
    if "把手给我" in text:
        hits.append("把手给我")

    for old, new in (
        ("往你", "往自己"),
        ("向你", "向自己"),
        ("递给你", "放在自己手边"),
        ("塞给你", "放在自己手边"),
        ("交给你", "放在自己手边"),
        ("你手背", "自己手背"),
        ("你手上", "自己手上"),
        ("你的手", "自己的手"),
        ("碰你", "收回手"),
        ("牵你", "收回手"),
        ("抱你", "收回手"),
        ("摸你", "收回手"),
    ):
        if old in text:
            hits.append(old)
            text = text.replace(old, new)

    if hits:
        if user_known:
            return "我够不到你，等你过来再说。", hits
        return "你还没告诉我你在哪儿呢——我够不到你。", hits
    return text, hits


def apply_intimacy_filter(text: str, level: str, fallback: str) -> tuple[str, bool]:
    """默认档位下，命中露骨词就整条换成温和回应，不解释。"""

    if not text:
        return text, False
    low = text.lower()
    for word in EXPLICIT_WORDS:
        if word.lower() in low:
            return fallback, True
    return text, False


def tidy(text: str) -> str:
    """收一下多余空行与行尾空格，保留原来的分条节奏。"""

    text = re.sub(r"[ \t]+\n", "\n", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def looks_empty(text: str) -> bool:
    stripped = re.sub(r"[（(][^（）()]*[）)]|[\s。！？!?；;，,、…·]", "", text or "")
    return not stripped
