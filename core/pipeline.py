"""一轮回复的完整处理链：剥离状态块 → 回写现场 → 去屏幕化 → 补动作。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .guard import (
    apply_intimacy_filter,
    de_mediate,
    ensure_action,
    looks_empty,
    strip_away_contact,
    tidy,
)
from .models import PresenceState
from .parser import extract_state_block, heuristic_patch, parse_actions
from .settings import RuntimeSettings


@dataclass
class ProcessedReply:
    text: str
    notes: list[str] = field(default_factory=list)
    hits: list[str] = field(default_factory=list)
    had_block: bool = False
    blocked: bool = False


def _filter_patch(patch: dict, together: bool) -> dict:
    """不在一起的时候，拒绝一切"碰到她/递给她"的状态变更。"""

    if together:
        return patch
    blocked_keys = {"contacts", "contact_add", "release", "distance", "pending"}
    return {k: v for k, v in patch.items() if k not in blocked_keys}


def process_output(
    raw: str,
    state: PresenceState,
    now: datetime,
    settings: RuntimeSettings,
) -> ProcessedReply:
    stamp = now.timestamp()
    clean, patch, found = extract_state_block(raw or "")

    notes: list[str] = []
    if patch:
        notes.extend(state.apply_patch(_filter_patch(patch, state.together), stamp))

    for action in parse_actions(clean):
        state.note_action(action, settings.action_history)

    if not found:
        guessed = heuristic_patch(clean, state)
        if guessed:
            notes.extend(
                state.apply_patch(_filter_patch(guessed, state.together), stamp)
            )

    hits: list[str] = []
    text = clean
    if settings.rewrite_reply:
        text, _, hits = de_mediate(text, settings.extra_banned)

    if not state.together:
        text, away_hits = strip_away_contact(text, state.user_place_known)
        hits.extend(away_hits)

    text, blocked = apply_intimacy_filter(
        text, settings.intimacy_level, settings.fallback_line
    )
    if blocked:
        hits.append("blocked")

    if settings.force_action:
        text = ensure_action(text, state, settings.label, state.recent_actions)

    if not text.strip() or looks_empty(text):
        text = settings.fallback_line

    state.updated_at = stamp
    return ProcessedReply(
        text=tidy(text),
        notes=notes,
        hits=hits or [],
        had_block=found,
        blocked=blocked,
    )
