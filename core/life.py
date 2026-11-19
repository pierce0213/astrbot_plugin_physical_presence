"""她的一天：不是围着用户转的日程，而是她自己要上学、要出门。

插件只做两件事：
1. 到点了把她放到该在的地方（教室/食堂/图书馆/公交/家）；
2. 按 follow_mode 决定这一段时间你在不在她旁边。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LifeBlock:
    start: str
    end: str
    place_key: str
    activity: str
    with_user: bool = True

    def label(self) -> str:
        return f"{self.start}-{self.end}"


@dataclass
class LifePlan:
    identity: str
    blocks: list[LifeBlock]
    source: str = "builtin"

    def block_at(self, now: datetime) -> LifeBlock | None:
        current = now.strftime("%H:%M")
        for block in self.blocks:
            if block.start <= block.end:
                if block.start <= current < block.end:
                    return block
            elif current >= block.start or current < block.end:
                return block
        return None

    def describe(self) -> str:
        lines = [f"她的一天（{self.identity}）："]
        for block in self.blocks:
            mark = "在一起" if block.with_user else "不在你身边"
            lines.append(
                f"{block.label()} · {block.place_key} · {block.activity}（{mark}）"
            )
        return "\n".join(lines)


STUDENT_BLOCKS = [
    LifeBlock("07:00", "07:40", "home", "起床、洗漱，在餐桌边吃早饭", True),
    LifeBlock("07:40", "08:10", "bus", "去学校，靠窗站着，手抓着扶杆", False),
    LifeBlock("08:10", "11:40", "classroom", "上午的课，笔记记到一半", False),
    LifeBlock("11:40", "12:30", "canteen", "在食堂吃午饭，餐盘推到对面", False),
    LifeBlock("12:30", "13:20", "library", "趴在桌上眯一会儿，书还摊着", False),
    LifeBlock("13:20", "16:50", "classroom", "下午的课，笔尖在纸上打转", False),
    LifeBlock("16:50", "17:40", "park", "绕操场走两圈，外套搭在臂弯", True),
    LifeBlock("17:40", "18:20", "convenience", "买瓶水，顺手在冷柜前站一会儿", True),
    LifeBlock("18:20", "19:20", "home", "一起做晚饭，锅里的水刚开", True),
    LifeBlock("19:20", "22:30", "home", "在茶几边写作业，电视开着没看", True),
    LifeBlock("22:30", "07:00", "home", "睡下，被子拉到下巴", True),
]

WORKER_BLOCKS = [
    LifeBlock("07:30", "08:20", "home", "早饭，边吃边看手机上的日程", True),
    LifeBlock("08:20", "09:00", "bus", "通勤，站在车门边", False),
    LifeBlock("09:00", "12:00", "office", "在工位上处理文件，肩膀前倾", False),
    LifeBlock("12:00", "13:00", "canteen", "和同事拼桌吃午饭", False),
    LifeBlock("13:00", "18:00", "office", "开会、回邮件，杯子里的水凉了", False),
    LifeBlock("18:00", "18:40", "bus", "回家，靠着车窗", False),
    LifeBlock("18:40", "23:00", "home", "晚饭，然后在沙发上摊开", True),
]

FREELANCE_BLOCKS = [
    LifeBlock("08:00", "09:00", "home", "起床，头发乱着去厨房烧水", True),
    LifeBlock("09:00", "12:00", "home", "在餐桌上写东西，写两行停一下", True),
    LifeBlock("12:00", "13:00", "kitchen", "煮面，围裙带子松了", True),
    LifeBlock("13:00", "17:30", "home", "继续写，脚搭在椅子横杆上", True),
    LifeBlock("17:30", "18:30", "park", "出去走一圈，买杯奶茶", True),
    LifeBlock("18:30", "23:00", "home", "回来做饭，晚上窝在沙发", True),
]

IDENTITY_BLOCKS = {
    "学生": STUDENT_BLOCKS,
    "上班族": WORKER_BLOCKS,
    "自由职业": FREELANCE_BLOCKS,
}

HOME_PLACES = {"home", "kitchen", "yard"}


def build_plan(identity: str = "学生", follow_mode: str = "together") -> LifePlan:
    identity = identity if identity in IDENTITY_BLOCKS else "学生"
    blocks = [
        LifeBlock(
            block.start,
            block.end,
            block.place_key,
            block.activity,
            _with_user(block, follow_mode),
        )
        for block in IDENTITY_BLOCKS[identity]
    ]
    return LifePlan(identity=identity, blocks=blocks, source="builtin")


def _with_user(block: LifeBlock, follow_mode: str) -> bool:
    if follow_mode == "together":
        return True
    if follow_mode == "home_only":
        return block.place_key in HOME_PLACES
    # separate：按她自己的安排，只有本来就在一起的时间段才在
    return block.with_user
