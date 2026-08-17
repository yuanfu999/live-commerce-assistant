"""话术数据模型"""
from dataclasses import dataclass, field
from typing import Optional
import time


# 话术类型
SCRIPT_TYPE_MAIN = "main"           # 商品主讲
SCRIPT_TYPE_TRANSITION = "transition"  # 过渡话术
SCRIPT_TYPE_URGE = "urge"           # 促单话术
SCRIPT_TYPE_OPENING = "opening"     # 开场白
SCRIPT_TYPE_CLOSING = "closing"     # 收场白
SCRIPT_TYPE_DANMAKU = "danmaku"     # 弹幕回复
SCRIPT_TYPE_TIMER = "timer"         # 定时播报

# 话术风格
STYLE_PROMO = "热情促销型"
STYLE_REVIEW = "专业测评型"
STYLE_PARENTING = "亲子教育型"
STYLE_CUSTOM = "自定义"


@dataclass
class Script:
    """话术"""
    id: int = 0
    product_id: int = 0             # 关联商品ID（0=通用话术）
    script_type: str = SCRIPT_TYPE_MAIN
    content: str = ""               # 话术内容
    style: str = STYLE_PROMO        # 风格
    is_favorite: bool = False       # 是否收藏
    play_count: int = 0            # 播放次数
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "script_type": self.script_type,
            "content": self.content,
            "style": self.style,
            "is_favorite": self.is_favorite,
            "play_count": self.play_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Script":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
