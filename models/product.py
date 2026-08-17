"""商品数据模型"""
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class Product:
    """商品信息"""
    id: int = 0
    name: str = ""                    # 商品名称
    price: str = ""                   # 价格
    feature: str = ""                 # 特点/卖点
    target_audience: str = ""         # 适合人群
    benefit: str = ""                 # 好处/价值
    commission: str = ""              # 佣金
    extra_notes: str = ""             # 自定义补充话术
    enabled: bool = True              # 是否启用
    priority: int = 0                 # 排序优先级
    scripts_per_round: int = 5        # 每轮播报几条话术
    max_rounds: int = 0              # 最大轮次（0=无限循环）
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "feature": self.feature,
            "target_audience": self.target_audience,
            "benefit": self.benefit,
            "commission": self.commission,
            "extra_notes": self.extra_notes,
            "enabled": self.enabled,
            "priority": self.priority,
            "scripts_per_round": self.scripts_per_round,
            "max_rounds": self.max_rounds,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Product":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
