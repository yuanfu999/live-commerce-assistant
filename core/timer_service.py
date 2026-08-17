"""定时播报服务 - 报时、自定义提醒、AI生成文案"""
import time
import threading
from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal
from typing import List, Optional

from core import app_logger


class TimerService(QThread):
    """
    定时播报服务（QThread后台运行）
    
    支持两种播报内容模式：
    - custom: 轮换播报用户自定义文案
    - ai: 根据用户提示词由AI实时生成文案
    
    信号：
        trigger_text: 触发一条播报文本
        status_changed: 状态变化
    """
    trigger_text = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._stop_event = threading.Event()

        # 配置
        self.enabled = False
        self.interval_minutes = 10
        self.announce_time = True
        self.mode = "custom"           # custom / ai
        self.ai_prompt = ""            # AI生成模式的提示词
        self.messages: List[str] = []
        self.ai_engine = None          # AIEngine实例（由主窗口注入）
        self._msg_index = 0
        self._last_trigger_time = 0

    def start_service(self):
        """启动定时服务"""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._last_trigger_time = time.time()
        self.start()
        self.status_changed.emit("定时播报已开启")

    def stop_service(self):
        """停止定时服务"""
        self._running = False
        self._stop_event.set()
        self.status_changed.emit("定时播报已关闭")

    def run(self):
        """定时服务主循环"""
        while self._running and not self._stop_event.is_set():
            # 每10秒检查一次
            self._stop_event.wait(10)
            if self._stop_event.is_set():
                break

            now = datetime.now()
            elapsed = time.time() - self._last_trigger_time

            # 整点/半点报时
            if self.announce_time:
                if now.minute == 0 and now.second < 15:
                    hour = now.hour
                    if hour > 12:
                        time_str = f"晚上{hour - 12}点整"
                    elif hour == 12:
                        time_str = "中午12点整"
                    else:
                        time_str = f"上午{hour}点整"
                    text = f"现在是{time_str}，刚进来的家人们点点关注，主播正在给大家讲解好物！"
                    self.trigger_text.emit(text)
                    self._last_trigger_time = time.time()
                    continue
                elif now.minute == 30 and now.second < 15:
                    hour = now.hour
                    if hour > 12:
                        time_str = f"晚上{hour - 12}点半"
                    elif hour == 12:
                        time_str = "中午12点半"
                    else:
                        time_str = f"上午{hour}点半"
                    text = f"现在是{time_str}，感谢还在直播间的家人们！没点关注的点点关注哦！"
                    self.trigger_text.emit(text)
                    self._last_trigger_time = time.time()
                    continue

            # 自定义间隔提醒
            if elapsed >= self.interval_minutes * 60:
                text = self._get_next_text()
                if text:
                    self.trigger_text.emit(text)
                    self._last_trigger_time = time.time()

    def _get_next_text(self) -> str:
        """根据模式获取下一条播报文本"""
        if self.mode == "ai":
            text = self._generate_ai_text()
            if text:
                return text
            # AI生成失败时回退到自定义文案（如有）
            if self.messages:
                app_logger.log_warn("定时播报AI生成失败，回退使用自定义文案")
            else:
                return ""
        # 自定义文案轮换
        if not self.messages:
            return ""
        msg = self.messages[self._msg_index % len(self.messages)]
        self._msg_index += 1
        return msg

    def _generate_ai_text(self) -> str:
        """调用AI生成一条直播提醒文案"""
        if not self.ai_engine:
            return ""
        prompt = self.ai_prompt or "生成一条直播间提醒话术"
        system_prompt = (
            "你是一个直播带货主播的文案助手。"
            "请根据用户的要求生成一条直播口播提醒话术，"
            "要求口语化、有亲和力、适合直接播报，长度50-150字，"
            "只输出话术内容本身，不要加任何前缀、编号或解释。"
        )
        try:
            result = self.ai_engine.chat(
                prompt, system_prompt=system_prompt, temperature=1.0, max_tokens=300
            )
            text = (result or "").strip().strip('"“”').strip()
            # 去掉可能的前缀编号
            for prefix in ("1.", "1、", "- ", "· "):
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
            if text:
                app_logger.log_info("定时播报AI生成文案: " + text[:40])
            return text
        except Exception as e:
            app_logger.log_error("定时播报AI生成失败: " + str(e)[:100])
            return ""
