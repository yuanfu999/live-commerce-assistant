"""配置数据模型"""
from dataclasses import dataclass, field
from typing import List, Optional
import json
import os


@dataclass
class ModelConfig:
    """AI模型配置"""
    name: str = ""                  # 配置名称（如"本地Ollama"）
    base_url: str = ""              # API地址
    api_key: str = ""               # API Key
    model_name: str = ""            # 模型名称
    is_active: bool = False         # 是否当前使用


@dataclass
class VoiceConfig:
    """语音配置"""
    tts_voice: str = "zh-CN-YunxiNeural"   # edge-tts音色
    speed: float = 1.0                     # 语速倍率
    volume: int = 100                      # 音量(0-100)
    enable_voice_change: bool = False      # 是否开启变声
    voice_change_speed: float = 1.3        # 变声加速倍率
    output_device: str = "default"         # 输出设备


@dataclass
class BroadcastConfig:
    """播报配置"""
    pause_between_scripts: float = 2.0     # 话术间隔秒数
    auto_loop: bool = True                 # 全部播完是否循环
    mode: str = "auto"                     # auto/manual/danmaku_priority


@dataclass
class TimerConfig:
    """定时播报配置"""
    enabled: bool = False
    interval_minutes: int = 10             # 间隔分钟
    announce_time: bool = True             # 是否报时
    mode: str = "custom"                   # custom=自定义文案 / ai=AI生成文案
    ai_prompt: str = ""                    # AI生成模式的提示词
    messages: List[str] = field(default_factory=lambda: [
        "家人们，点关注不迷路，主播每天准时开播！",
        "刚进来的宝宝们，点点关注，一会儿有福利哦！",
    ])


@dataclass
class DanmakuConfig:
    """弹幕互动配置"""
    enabled: bool = False
    room_url: str = ""                     # 直播间URL
    reply_interval: int = 30               # 回复最小间隔(秒)
    welcome_enabled: bool = True           # 欢迎语
    thanks_enabled: bool = True            # 感谢语
    keywords: List[str] = field(default_factory=lambda: [
        "多少钱", "怎么买", "有优惠", "几岁", "适合", "质量", "退货"
    ])


@dataclass
class AppConfig:
    """应用总配置"""
    models: List[ModelConfig] = field(default_factory=lambda: [
        ModelConfig(
            name="本地Ollama",
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model_name="qwen2.5:7b",
            is_active=True,
        ),
    ])
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    broadcast: BroadcastConfig = field(default_factory=BroadcastConfig)
    timer: TimerConfig = field(default_factory=TimerConfig)
    danmaku: DanmakuConfig = field(default_factory=DanmakuConfig)
    show_guide: bool = True  # 首次启动是否显示快速入门引导
    custom_script_prompt: str = ""  # 用户自定义话术生成提示词

    def get_active_model(self) -> Optional[ModelConfig]:
        for m in self.models:
            if m.is_active:
                return m
        return self.models[0] if self.models else None

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "models": [m.__dict__ for m in self.models],
            "voice": self.voice.__dict__,
            "broadcast": self.broadcast.__dict__,
            "timer": self.timer.__dict__,
            "danmaku": self.danmaku.__dict__,
            "show_guide": self.show_guide,
            "custom_script_prompt": self.custom_script_prompt,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "AppConfig":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            config = cls()
            if "models" in data:
                config.models = [ModelConfig(**m) for m in data["models"]]
            if "voice" in data:
                config.voice = VoiceConfig(**data["voice"])
            if "broadcast" in data:
                config.broadcast = BroadcastConfig(**data["broadcast"])
            if "timer" in data:
                config.timer = TimerConfig(**{
                    k: v for k, v in data["timer"].items()
                    if k in TimerConfig.__dataclass_fields__
                })
            if "danmaku" in data:
                config.danmaku = DanmakuConfig(**{
                    k: v for k, v in data["danmaku"].items()
                    if k in DanmakuConfig.__dataclass_fields__
                })
            if "show_guide" in data:
                config.show_guide = bool(data["show_guide"])
            if "custom_script_prompt" in data:
                config.custom_script_prompt = str(data["custom_script_prompt"])
            return config
        except Exception:
            return cls()
