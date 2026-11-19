"""每轮上下文预算：第一次/状态变化发全量，稳定轮只发变化。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from .models import PresenceState
from .render import render_protocol, render_state
from .settings import RuntimeSettings


def _state_signature(state: PresenceState) -> str:
    """只把模型真正需要重新知道的字段放进签名。"""

    payload = {
        "place": state.place_key,
        "detail": state.scene_detail,
        "her_pose": state.her_pose,
        "user_known": state.user_place_known,
        "user_place": state.user_place_key,
        "user_pose_known": state.user_pose_known,
        "user_pose": state.you_pose,
        "together": state.together,
        "distance": state.distance_cm,
        "activity": state.activity,
        "pending": state.pending,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_injection(
    state: PresenceState,
    now: datetime,
    settings: RuntimeSettings,
    user_text: str = "",
) -> str:
    """第一次、换场景、换姿势、换手、接触变化时全量；其余稳定轮压缩。"""

    signature = _state_signature(state)
    first = not bool(state.context_sig)
    compact = not first and signature == state.context_sig

    text = render_state(
        state, now, settings, user_text, compact=compact
    ) + "\n\n" + render_protocol(
        settings,
        state.together,
        state.user_place_known,
        compact=not first,
    )
    state.context_sig = signature
    return text
