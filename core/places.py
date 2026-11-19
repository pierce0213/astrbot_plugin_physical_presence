"""地点注册表：她可以在家，也可以在教室、图书馆、食堂、公交上。

每个地点自带"这里通常有什么、两个人怎么坐、离多近"，
切换地点时现场跟着换，不会把家里的可乐带到教室里。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlacePreset:
    key: str
    name: str
    detail: str
    her_pose: str
    distance_cm: int
    props: tuple[str, ...] = field(default_factory=tuple)
    aliases: tuple[str, ...] = field(default_factory=tuple)


PLACES: dict[str, PlacePreset] = {
    "home": PlacePreset(
        key="home",
        name="家里",
        detail="客厅，沙发和茶几之间",
        her_pose="盘腿坐在地毯上，背靠着沙发",
        distance_cm=40,
        props=(
            "可乐 x3 | 冰箱 | 冰 | 罐身挂着水珠",
            "汤碗 | 茶几 | 温 | 还剩半碗",
            "毛毯 | 沙发扶手 | 常温 | 叠着",
            "拖鞋 | 玄关 | 常温 |",
        ),
        aliases=("家", "家里", "客厅", "小别墅", "沙发", "书桌", "宿舍小桌", "盥洗"),
    ),
    "bedroom": PlacePreset(
        key="bedroom",
        name="卧室",
        detail="床边，台灯还亮着",
        her_pose="侧躺在床上，被子拉到下巴",
        distance_cm=20,
        props=(
            "被子 | 床上 | 常温 | 拉到下巴",
            "枕头 | 床头 | 常温 | 压出一个浅窝",
            "台灯 | 床头柜 | 暖光 | 开着",
        ),
        aliases=("卧室", "床上", "床边", "床", "被子", "枕头", "宿舍", "寝室", "睡觉", "睡下"),
    ),
    "kitchen": PlacePreset(
        key="kitchen",
        name="厨房",
        detail="灶台和水槽之间",
        her_pose="站在灶台前，围裙带子系在腰后",
        distance_cm=60,
        props=(
            "水壶 | 灶台 | 热 | 刚烧开",
            "汤勺 | 锅里 | 温 | 木柄",
            "抹布 | 台面 | 湿 |",
        ),
        aliases=("厨房", "灶台", "做饭", "洗碗"),
    ),
    "yard": PlacePreset(
        key="yard",
        name="院子",
        detail="葡萄架下，两条小板凳",
        her_pose="坐在小板凳上，膝头摊着一小盆豆子",
        distance_cm=25,
        props=(
            "豆子 | 她膝头 | 常温 | 剥了一半",
            "搪瓷盆 | 地上 | 常温 | 装着豆壳",
            "猫玩具 | 地上 | 常温 | 毛线球",
        ),
        aliases=("院子", "院里", "葡萄架", "小院"),
    ),
    "classroom": PlacePreset(
        key="classroom",
        name="教室",
        detail="倒数第二排，靠窗的两个位置",
        her_pose="坐在倒数第二排靠窗的位置，课本摊在桌上，笔帽咬在嘴里",
        distance_cm=20,
        props=(
            "课本 | 桌上 | 常温 | 摊开在第三十二页",
            "笔袋 | 桌上 | 常温 | 拉链没拉",
            "保温杯 | 桌角 | 温 | 泡着茶",
        ),
        aliases=("教室", "上课", "学校", "班里", "课堂", "教学", "教学楼", "专业课", "选修课", "课间"),
    ),
    "library": PlacePreset(
        key="library",
        name="图书馆",
        detail="三楼靠窗的长桌",
        her_pose="在长桌边坐下来，把借的书立在桌上",
        distance_cm=80,
        props=(
            "借的书 | 桌上 | 常温 | 摊开到一半",
            "水杯 | 桌角 | 温 | 拧着盖",
            "耳塞 | 她手边 | 常温 | 装在小盒里",
        ),
        aliases=("图书馆", "自习", "自习室", "阅览室"),
    ),
    "canteen": PlacePreset(
        key="canteen",
        name="食堂",
        detail="二楼靠墙的双人桌",
        her_pose="在长桌边坐下来，餐盘放在面前",
        distance_cm=55,
        props=(
            "餐盘 | 桌上 | 热 | 两荤一素",
            "筷子 | 桌上 | 常温 | 一次性木筷",
            "纸巾 | 桌上 | 常温 | 抽了一半",
        ),
        aliases=("食堂", "饭堂", "打饭", "午饭", "晚饭"),
    ),
    "bus": PlacePreset(
        key="bus",
        name="公交车上",
        detail="最后一排靠窗的两个座位",
        her_pose="靠窗坐着，帆布包放在膝上，肩膀随着车晃",
        distance_cm=15,
        props=(
            "帆布包 | 她膝上 | 常温 | 拉链开着",
            "公交卡 | 她手里 | 常温 |",
        ),
        aliases=("公交", "公交车", "地铁", "车上", "路上"),
    ),
    "convenience": PlacePreset(
        key="convenience",
        name="便利店",
        detail="冷柜旁边的过道",
        her_pose="站在冷柜前，门开着，冷气扑到脸上",
        distance_cm=30,
        props=(
            "可乐 | 冷柜 | 冰 | 一排排立着",
            "关东煮 | 柜台 | 热 | 冒着气",
            "购物篮 | 你手里 | 常温 | 空的",
        ),
        aliases=("便利店", "超市", "小卖部", "冷柜"),
    ),
    "park": PlacePreset(
        key="park",
        name="公园",
        detail="湖边的长椅",
        her_pose="坐在长椅上，腿悬着晃，风把头发吹到脸侧",
        distance_cm=20,
        props=(
            "奶茶 | 长椅 | 温 | 插着吸管",
            "外套 | 长椅 | 常温 | 她脱下来的",
        ),
        aliases=("公园", "湖边", "长椅", "散步", "操场"),
    ),
    "street": PlacePreset(
        key="street",
        name="街上",
        detail="旧书街区的骑楼下，旁边是一家唱片店",
        her_pose="走在前半步，帆布包带子压在肩上，时不时回头",
        distance_cm=30,
        props=(
            "旧书 | 你手里 | 常温 | 纸页发黄",
            "奶茶 | 她手里 | 温 | 插着吸管",
            "帆布包 | 她肩上 | 常温 | 拉链开着",
        ),
        aliases=("街", "街区", "旧书街", "校外", "咖啡", "小店", "路上"),
    ),
    "office": PlacePreset(
        key="office",
        name="办公室",
        detail="她的工位旁边",
        her_pose="坐在工位上，肩膀前倾，盯着桌上的文件",
        distance_cm=50,
        props=(
            "文件 | 桌上 | 常温 | 摊着",
            "咖啡 | 桌角 | 热 | 还剩一半",
        ),
        aliases=("公司", "办公室", "工位", "上班"),
    ),
}

DEFAULT_PLACE = "home"


def get_place(key: str | None) -> PlacePreset:
    return PLACES.get(str(key or ""), PLACES[DEFAULT_PLACE])


def match_place(text: str | None) -> PlacePreset | None:
    """从"地点：教室"或日程里的活动文字里认出地点。"""

    haystack = str(text or "")
    if not haystack:
        return None
    for preset in PLACES.values():
        if preset.name in haystack:
            return preset
    best: tuple[int, PlacePreset] | None = None
    for preset in PLACES.values():
        for alias in preset.aliases:
            if alias and alias in haystack:
                if best is None or len(alias) > best[0]:
                    best = (len(alias), preset)
    return best[1] if best else None
