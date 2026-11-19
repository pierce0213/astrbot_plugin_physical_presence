"""没有虚拟人生数据时的穿搭兜底：按季节和日期稳定地选一套。"""

from __future__ import annotations

import zlib
from datetime import datetime

SEASON_POOLS = {
    "春": {
        "top": ["浅色棉衬衫", "薄针织开衫", "白色圆领卫衣"],
        "bottom": ["浅蓝直筒牛仔裤", "米色半身裙", "灰色运动裤"],
        "shoes": ["白色帆布鞋", "浅棕乐福鞋"],
        "outer": ["薄风衣", "牛仔外套"],
        "hair": ["松松扎在脑后", "披着，别了一枚小夹子"],
        "scent": ["洗衣液的味道", "一点柑橘味"],
    },
    "夏": {
        "top": ["白色短袖衬衫", "浅蓝吊带外搭薄衬衫", "棉质短袖"],
        "bottom": ["浅色阔腿裤", "深色短裤", "棉麻长裙"],
        "shoes": ["帆布鞋", "凉鞋"],
        "outer": ["不穿外套", "薄防晒衫"],
        "hair": ["高高扎起", "编成一条松辫子"],
        "scent": ["洗完澡的皂味", "一点薄荷"],
    },
    "秋": {
        "top": ["浅色衬衫", "燕麦色针织衫", "深蓝卫衣"],
        "bottom": ["深色直筒裤", "卡其长裙", "牛仔裤"],
        "shoes": ["短靴", "白色帆布鞋"],
        "outer": ["深色薄外套", "针织开衫"],
        "hair": ["松松扎在脑后", "披着，被风吹到脸侧"],
        "scent": ["洗衣液的味道", "一点雪松"],
    },
    "冬": {
        "top": ["厚针织毛衣", "加绒衬衫", "高领打底"],
        "bottom": ["加绒直筒裤", "厚长裙"],
        "shoes": ["加绒短靴", "厚底鞋"],
        "outer": ["长款羽绒服", "呢子大衣"],
        "hair": ["扎起来，免得压到领子", "披着，发尾有点毛躁"],
        "scent": ["围巾上残留的暖香", "一点木质香"],
    },
}


def season_of(now: datetime) -> str:
    month = now.month
    if 3 <= month <= 5:
        return "春"
    if 6 <= month <= 8:
        return "夏"
    if 9 <= month <= 11:
        return "秋"
    return "冬"


def outfit_for(now: datetime, identity: str = "学生") -> str:
    season = season_of(now)
    pool = SEASON_POOLS[season]
    seed = int(now.strftime("%Y%m%d")) + zlib.crc32(identity.encode("utf-8"))

    def pick(key: str) -> str:
        items = pool[key]
        return items[seed % len(items)]

    return (
        f"{pick('top')}配{pick('bottom')}，{pick('outer')}，脚上{pick('shoes')}；"
        f"头发{pick('hair')}，身上是{pick('scent')}。"
    )
